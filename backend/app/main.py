from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import logging
from urllib.parse import urlsplit
from threading import Lock
from pathlib import Path
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, computed_field
from starlette.concurrency import run_in_threadpool

from .database import connect, initialize
from .records import RequestConflict, save_record
from .progression import progression
from .prediction import MockPredictor, Prediction, PredictionUnavailableError, Predictor, TrainedTomatoPredictor
from .image_validation import (MAX_IMAGE_BYTES, PlantImageValidator, TechnicalPlantImageValidator,
                               ValidationResult, image_extension)
from .plant_suitability import PlantContentVerifier, Suitability
from .startup import startup_stage
from .request_limits import LocalRequestBoundary
from .diagnostics import RequestDiagnostics, event, stage

ROOT = Path(__file__).resolve().parents[2]


class PlantInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    crop_name: str | None = Field(default=None, min_length=1, max_length=100)


class Plant(PlantInput):
    id: str
    created_at: str


class PlantCreate(PlantInput):
    request_id: str | None = Field(default=None, min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


class PlantCropUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    crop_name: str | None = Field(default=None, min_length=1, max_length=100)


class Observation(BaseModel):
    id: str
    plant_id: str
    image_path: str
    created_at: str
    disease: str | None = None
    severity: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=100)
    predictor: str | None = None
    is_mock: bool
    analysis_status: Literal['not_requested', 'completed', 'legacy_unknown'] = 'legacy_unknown'
    observed_at: str | None = None
    observed_timezone: str | None = None
    tracking_ref: str | None = None
    notes: str | None = None
    image_sha256: str | None = None
    request_id: str | None = None
    duplicate_of: str | None = None
    checkpoint_id: str | None = None
    severity_source: str | None = None
    severity_method: str | None = None
    severity_version: str | None = None
    severity_scale: str | None = None
    @computed_field
    @property
    def prediction_score(self) -> float | None:
        """Uncalibrated softmax percentage for real analyses; no score for mock records."""
        return self.confidence if not self.is_mock and self.analysis_status == 'completed' else None

    temperature: float | None = None
    humidity: float | None = None
    soil_type: str | None = None
    soil_condition: Literal["Dry", "Normal", "Wet"] | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def read_image(upload: UploadFile) -> bytes:
    try:
        return await upload.read(MAX_IMAGE_BYTES + 1)
    finally:
        await upload.close()


def create_app(database_path: Path | None = None, upload_dir: Path | None = None,
               predictor: Predictor | None = None,
               validator: PlantImageValidator | None = None,
               checkpoint_path: Path | None = None,
               plant_verifier: PlantContentVerifier | None = None) -> FastAPI:
    production = os.getenv('AGRISENSE_ENV', 'development').strip().lower() == 'production'
    database_path = database_path or Path(os.getenv("AGRISENSE_DB_PATH", ROOT / "database/agrisense.db"))
    upload_dir = upload_dir or Path(os.getenv("AGRISENSE_UPLOAD_DIR", ROOT / "backend/uploads"))
    configured_hosts = []
    if production:
        configured_hosts = [host.strip() for host in os.getenv('AGRISENSE_ALLOWED_HOSTS', '').split(',') if host.strip()]
        if not configured_hosts or '*' in configured_hosts:
            raise RuntimeError('Production requires explicit AGRISENSE_ALLOWED_HOSTS; wildcard hosts are forbidden.')
        for name, path in (('AGRISENSE_DB_PATH', database_path), ('AGRISENSE_UPLOAD_DIR', upload_dir)):
            resolved_path = path.resolve()
            if not path.is_absolute() or resolved_path == ROOT.resolve() or ROOT.resolve() in resolved_path.parents:
                raise RuntimeError(f'Production requires {name} to be an absolute persistent path outside the source tree.')
        configured_origins = [origin.strip() for origin in os.getenv('AGRISENSE_CORS_ORIGINS', '').split(',') if origin.strip()]
        if any(
            origin == '*' or
            (parsed := urlsplit(origin)).scheme != 'https' or not parsed.hostname or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.password
            for origin in configured_origins
        ):
            raise RuntimeError('Production browser CORS origins must be exact HTTPS origins; native apps need no CORS entry.')
        for name in ('AGRISENSE_CHECKPOINT_PATH', 'AGRISENSE_PLANT_VERIFIER_WEIGHTS'):
            artifact = Path(os.getenv(name, ''))
            if not artifact.is_absolute() or not artifact.is_file():
                raise RuntimeError(f'Production requires an existing absolute {name}; model downloads are disabled.')
    configured_checkpoint = checkpoint_path or Path(os.getenv(
        "AGRISENSE_CHECKPOINT_PATH", ROOT / "model/checkpoints/tomato_gpu_epoch5_retry2/best.pt"))
    if not configured_checkpoint.is_absolute():
        configured_checkpoint = ROOT / configured_checkpoint
    inference_lock = Lock()
    validator = validator or TechnicalPlantImageValidator()
    upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal predictor, plant_verifier
        with startup_stage('database'):
            initialize(database_path)
        if predictor is None:
            try:
                with startup_stage('tomato_checkpoint'):
                    predictor = await run_in_threadpool(TrainedTomatoPredictor, configured_checkpoint)
            except Exception:
                logging.getLogger('uvicorn.error').warning('Tomato analysis unavailable; record-only saving remains enabled.')
        if plant_verifier is None and isinstance(predictor, TrainedTomatoPredictor):
            try:
                with startup_stage('plant_suitability'):
                    plant_verifier = await run_in_threadpool(PlantContentVerifier)
            except Exception:
                logging.getLogger('uvicorn.error').warning('Plant screening unavailable; tomato analysis remains disabled.')
        app.state.predictor = predictor
        app.state.plant_verifier = plant_verifier
        logging.getLogger('uvicorn.error').info('AgriSense startup state=ready record_only=true tomato_analysis=%s',
                                              isinstance(predictor, TrainedTomatoPredictor) and plant_verifier is not None)
        yield

    app = FastAPI(title="AgriSense: Plant Disease Detection and Health Monitoring Using Hybrid CNN-Transformer Architecture", lifespan=lifespan,
                  description="Local plant observation journal. Record-only saving requires no model.",
                  docs_url=None if production else '/docs', redoc_url=None if production else '/redoc',
                  openapi_url=None if production else '/openapi.json')
    origins = [origin.strip() for origin in os.getenv(
        'AGRISENSE_CORS_ORIGINS', '' if production else 'http://localhost:8081,http://127.0.0.1:8081').split(',') if origin.strip()]
    app.add_middleware(LocalRequestBoundary, allowed_origins=origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
    app.add_middleware(RequestDiagnostics)
    if production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=configured_hosts)
    # Stored image files are private journal content. Until authenticated,
    # owner-scoped photo delivery exists, production mode must not expose them.
    if not production:
        app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

    def require_plant(plant_id: str):
        with connect(database_path) as db:
            plant = db.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
        if plant is None:
            raise HTTPException(404, "Plant not found.")
        return dict(plant)

    @app.get("/health")
    def health():
        ready = isinstance(predictor, TrainedTomatoPredictor)
        screening_ready = plant_verifier is not None
        return {"status": "ok", "prediction_mode": "real tomato model" if ready else "unavailable",
                "is_mock": isinstance(predictor, MockPredictor),
                "capabilities": {"record_only": True, "technical_image_validation": True,
                                 "plant_content_screening": screening_ready,
                                 "tomato_analysis": ready and screening_ready,
                                 "severity_measurement": False, "health_progression": False},
                "analysis_message": ("Tomato classification available. Scores are uncalibrated; "
                                     "plant content screening enabled; results remain uncertain. Severity is unavailable." if ready and screening_ready else
                                     "Tomato analysis unavailable because the tomato model or plant-content screening is unavailable. You can still save without analysis." if ready else
                                     "Tomato analysis unavailable. You can still save without analysis.")}

    @app.get('/ready')
    def ready():
        model_ready = isinstance(predictor, TrainedTomatoPredictor) and plant_verifier is not None
        try:
            with connect(database_path) as db:
                db.execute('SELECT 1')
            database_ready = True
        except Exception:
            database_ready = False
        if not database_ready or not model_ready:
            return Response(content='Not ready', status_code=503, media_type='text/plain')
        return {'status': 'ready'}


    @app.post("/plants", response_model=Plant, status_code=201)
    def add_plant(body: PlantCreate, response: Response):
        # Optional client identity makes a lost-response retry safe without changing
        # existing journals or conflating different plants with the same name.
        plant_id = uuid5(NAMESPACE_URL, 'agrisense:plant:' + body.request_id) if body.request_id else uuid4()
        plant = {"id": str(plant_id), "name": body.name, "created_at": now(), "crop_name": body.crop_name}
        with connect(database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM plants WHERE id = ?', (plant['id'],)).fetchone()
            if existing is not None:
                if existing['name'] != body.name or existing['crop_name'] != body.crop_name:
                    raise HTTPException(409, 'This plant request ID was already used with different details.')
                response.status_code = 200
                return dict(existing)
            db.execute("INSERT INTO plants (id, name, created_at, crop_name) VALUES (:id, :name, :created_at, :crop_name)", plant)
        return plant

    @app.get("/plants", response_model=list[Plant])
    def list_plants():
        with connect(database_path) as db:
            return [dict(row) for row in db.execute("SELECT * FROM plants ORDER BY created_at DESC")]

    @app.get("/plants/{plant_id}", response_model=Plant)
    def get_plant(plant_id: str):
        return require_plant(plant_id)

    @app.patch("/plants/{plant_id}", response_model=Plant)
    def update_plant_crop(plant_id: str, body: PlantCropUpdate):
        # Crop labels are explicit user-supplied metadata; never infer them from a name.
        require_plant(plant_id)
        with connect(database_path) as db:
            db.execute("UPDATE plants SET crop_name = ? WHERE id = ?", (body.crop_name, plant_id))
            return dict(db.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone())

    @app.get("/plants/{plant_id}/observations", response_model=list[Observation])
    def observations(plant_id: str):
        require_plant(plant_id)
        with connect(database_path) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM observations WHERE plant_id = ? ORDER BY COALESCE(observed_at, created_at), created_at, id", (plant_id,))]

    @app.get('/plants/{plant_id}/progression')
    def plant_progression(plant_id: str, tracking_ref: Annotated[str | None, Query(max_length=100)] = None):
        # No comparison policy is enabled. Query parameters cannot supply measurements or thresholds.
        return progression(observations(plant_id), tracking_ref.strip() if tracking_ref else None)

    async def validated_image(upload: UploadFile) -> tuple[bytes, ValidationResult]:
        with stage('upload_read'):
            data = await read_image(upload)
        event('upload_received', bytes=len(data))
        with stage('image_validation'):
            validation = await run_in_threadpool(validator.validate, data)
        if not validation.is_valid:
            event('image_rejected', reason=validation.reason)
            status = 413 if validation.reason == "image_too_large" else (
                415 if validation.reason in {"unsupported_format", "invalid_image"} else 422)
            raise HTTPException(status, detail=validation.model_dump())
        return data, validation

    def check_suitability(data: bytes):
        if plant_verifier is None:
            raise HTTPException(503, detail={"code": "plant_screening_unavailable", "message":
                "Plant suitability screening is unavailable. No analysis or save was performed. Refresh model status and retry."})
        try:
            with stage('plant_screening'):
                suitability = plant_verifier.verify(data)
        except Exception as error:
            logging.getLogger(__name__).error('Plant-content screening failed: %s', type(error).__name__)
            raise HTTPException(503, detail={"code": "plant_screening_unavailable", "message":
                "Plant suitability screening failed. No analysis or save was performed. Refresh model status and retry."}) from error
        event('screening_result', outcome=suitability.outcome.value,
              plant_similarity=suitability.plant_similarity, unrelated_similarity=suitability.unrelated_similarity)
        if suitability.outcome == Suitability.NON_PLANT:
            raise HTTPException(422, detail={"code": "non_plant_image", "message": suitability.message})
        if suitability.outcome != Suitability.PLANT:
            raise HTTPException(422, detail={"code": "plant_content_uncertain", "message": suitability.message})
        return {"outcome": "plant", "message": suitability.message}

    @app.post('/check-plant-suitability')
    async def check_plant_suitability(image: Annotated[UploadFile, File()]):
        data, _ = await validated_image(image)
        def check():
            with inference_lock:
                return check_suitability(data)
        return await run_in_threadpool(check)

    def predict_image(data: bytes) -> Prediction:
        try:
            with inference_lock:
                if predictor is None:
                    raise HTTPException(503, detail={"code": "model_unavailable", "message":
                        "Tomato model is unavailable. No observation was saved. Refresh model status before retrying."})
                if plant_verifier is not None or isinstance(predictor, TrainedTomatoPredictor):
                    check_suitability(data)
                with stage('tomato_inference'):
                    return predictor.predict(data)
        except PredictionUnavailableError as error:
            # Do not leak model paths/errors, substitute a mock, or persist a failed scan.
            raise HTTPException(503, detail={"code": "inference_failed", "message":
                "Tomato inference failed. No observation was saved. Check backend logs, refresh model status and retry."}) from error

    @app.post("/validate-image", response_model=ValidationResult)
    async def validate_image(image: Annotated[UploadFile, File()]):
        _, validation = await validated_image(image)
        return validation

    @app.post("/predict", response_model=Prediction)
    async def predict(image: Annotated[UploadFile, File()]):
        data, _ = await validated_image(image)
        # Suitability is assessed separately from technical file validation and
        # disease inference. Rejection/abstention never produces or saves a label.
        return await run_in_threadpool(predict_image, data)

    @app.post('/plants/{plant_id}/records', response_model=Observation, status_code=201)
    async def add_record(
        plant_id: str, response: Response,
        image: Annotated[UploadFile, File()],
        request_id: Annotated[str, Form(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')],
        soil_condition: Annotated[Literal['Dry', 'Normal', 'Wet'], Form()],
        # Manually recorded context only; it is not sent to the disease model.
        # Supported temperature range is -50 to 70 °C, suitable for realistic
        # outdoor/greenhouse observations while rejecting likely unit mistakes.
        temperature: Annotated[float | None, Form(ge=-50, le=70, allow_inf_nan=False)] = None,
        humidity: Annotated[float | None, Form(ge=0, le=100, allow_inf_nan=False)] = None,
        soil_type: Annotated[str | None, Form(min_length=1, max_length=100)] = None,
        observed_at: Annotated[datetime | None, Form()] = None,
        observed_timezone: Annotated[str | None, Form(max_length=100)] = None,
        tracking_ref: Annotated[str | None, Form(max_length=100)] = None,
        notes: Annotated[str | None, Form(max_length=2000)] = None,
    ):
        require_plant(plant_id)
        soil_type = soil_type.strip() if soil_type is not None else None
        if soil_type == "":
            raise HTTPException(422, 'Soil type cannot be blank.')
        if observed_at is not None and (observed_at.tzinfo is None or observed_at > datetime.now(timezone.utc)):
            raise HTTPException(422, 'Observation time must include a timezone and must not be in the future.')
        fields = dict(request_id=request_id, observed_timezone=observed_timezone, temperature=temperature, humidity=humidity,
                      soil_type=soil_type, soil_condition=soil_condition,
                      observed_at=observed_at.astimezone(timezone.utc).isoformat() if observed_at else None,
                      tracking_ref=tracking_ref.strip() or None if tracking_ref else None,
                      notes=notes.strip() or None if notes else None)
        data, _ = await validated_image(image)
        try:
            saved, replay = await run_in_threadpool(
                save_record, database_path, upload_dir, plant_id, data,
                image_extension(data), fields, now())
        except RequestConflict as error:
            raise HTTPException(409, str(error)) from error
        if replay:
            response.status_code = 200
        return saved

    @app.post("/plants/{plant_id}/observations", response_model=Observation, status_code=201)
    async def add_observation(
        plant_id: str, response: Response,
        image: Annotated[UploadFile, File()],
        request_id: Annotated[str, Form(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')],
        temperature: Annotated[float | None, Form(ge=-50, le=70, allow_inf_nan=False)] = None,
        humidity: Annotated[float | None, Form(ge=0, le=100, allow_inf_nan=False)] = None,
        soil_type: Annotated[str | None, Form(min_length=1, max_length=100)] = None,
        soil_condition: Annotated[Literal["Dry", "Normal", "Wet"] | None, Form()] = None,
        observed_at: Annotated[datetime | None, Form()] = None,
        observed_timezone: Annotated[str | None, Form(max_length=100)] = None,
        tracking_ref: Annotated[str | None, Form(max_length=100)] = None,
        notes: Annotated[str | None, Form(max_length=2000)] = None,
    ):
        plant = require_plant(plant_id)
        if (plant['crop_name'] or '').strip().lower() != 'tomato':
            raise HTTPException(422, detail={"code": "unsupported_crop", "message":
                "Analysis supports tomato plants only. Select a plant known to be tomato, or save without analysis. The image screen does not identify species."})
        soil_type = soil_type.strip() if soil_type is not None else None
        if soil_type == "":
            raise HTTPException(422, "Soil type cannot be blank.")
        if observed_at is not None and (observed_at.tzinfo is None or observed_at > datetime.now(timezone.utc)):
            raise HTTPException(422, 'Observation time must include a timezone and must not be in the future.')
        fields = dict(request_id=request_id, observed_timezone=observed_timezone, temperature=temperature, humidity=humidity,
                      soil_type=soil_type, soil_condition=soil_condition,
                      observed_at=observed_at.astimezone(timezone.utc).isoformat() if observed_at else None,
                      tracking_ref=tracking_ref.strip() or None if tracking_ref else None,
                      notes=notes.strip() or None if notes else None)
        data, _ = await validated_image(image)
        # Only image bytes cross the predictor boundary. Persistence handles replay before inference.
        def analysis():
            result = predict_image(data)
            return dict(**result.model_dump(exclude={'prediction_score'}),
                        checkpoint_id=getattr(predictor, 'checkpoint_id', None))
        try:
            saved, replay = await run_in_threadpool(
                save_record, database_path, upload_dir, plant_id, data,
                image_extension(data), fields, now(), analysis)
        except RequestConflict as error:
            raise HTTPException(409, str(error)) from error
        if replay:
            response.status_code = 200
        event('observation_saved', replay=replay)
        return saved

    return app


app = create_app()
