from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import logging
from threading import Lock
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, computed_field
from starlette.concurrency import run_in_threadpool

from .database import connect, initialize
from .records import RequestConflict, save_record
from .progression import progression
from .prediction import MockPredictor, Prediction, PredictionUnavailableError, Predictor, TrainedTomatoPredictor
from .image_validation import (MAX_IMAGE_BYTES, PlantImageValidator, TechnicalPlantImageValidator,
                               ValidationResult, image_extension)
from .plant_suitability import PlantContentVerifier, Suitability

ROOT = Path(__file__).resolve().parents[2]


class PlantInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    crop_name: str | None = Field(default=None, min_length=1, max_length=100)


class Plant(PlantInput):
    id: str
    created_at: str


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
    database_path = database_path or Path(os.getenv("AGRISENSE_DB_PATH", ROOT / "database/agrisense.db"))
    upload_dir = upload_dir or Path(os.getenv("AGRISENSE_UPLOAD_DIR", ROOT / "backend/uploads"))
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
        initialize(database_path)
        if predictor is None:
            try:
                predictor = await run_in_threadpool(TrainedTomatoPredictor, configured_checkpoint)
            except Exception:
                logging.getLogger(__name__).exception("Tomato model unavailable at startup")
        if plant_verifier is None and isinstance(predictor, TrainedTomatoPredictor):
            try:
                plant_verifier = await run_in_threadpool(PlantContentVerifier)
            except Exception:
                logging.getLogger(__name__).exception("Plant-content screening unavailable at startup")
        app.state.predictor = predictor
        app.state.plant_verifier = plant_verifier
        yield

    app = FastAPI(title="AgriSense Phase 5", lifespan=lifespan,
                  description="Local plant observation journal. Record-only saving requires no model.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("AGRISENSE_CORS_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081").split(","),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
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


    @app.post("/plants", response_model=Plant, status_code=201)
    def add_plant(body: PlantInput):
        plant = {"id": str(uuid4()), "name": body.name, "created_at": now(), "crop_name": body.crop_name}
        with connect(database_path) as db:
            db.execute("INSERT INTO plants (id, name, created_at, crop_name) VALUES (:id, :name, :created_at, :crop_name)", plant)
        return plant

    @app.get("/plants", response_model=list[Plant])
    def list_plants():
        with connect(database_path) as db:
            return [dict(row) for row in db.execute("SELECT * FROM plants ORDER BY created_at DESC")]

    @app.get("/plants/{plant_id}", response_model=Plant)
    def get_plant(plant_id: str):
        return require_plant(plant_id)

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
        data = await read_image(upload)
        validation = validator.validate(data)
        if not validation.is_valid:
            status = 413 if validation.reason == "image_too_large" else (
                415 if validation.reason in {"unsupported_format", "invalid_image"} else 422)
            raise HTTPException(status, detail=validation.model_dump())
        return data, validation

    def check_suitability(data: bytes):
        if plant_verifier is None:
            raise PredictionUnavailableError('Plant-content screening is unavailable')
        try:
            suitability = plant_verifier.verify(data)
        except Exception as error:
            logging.getLogger(__name__).exception("Plant-content screening failed during request")
            raise PredictionUnavailableError('Plant-content screening failed') from error
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
        try:
            return await run_in_threadpool(check)
        except PredictionUnavailableError as error:
            raise HTTPException(503, detail={"code": "plant_screening_unavailable", "message":
                "Plant suitability screening is unavailable. No analysis or save was performed. Try again after refreshing model status."}) from error

    def predict_image(data: bytes) -> Prediction:
        try:
            with inference_lock:
                if predictor is None:
                    raise PredictionUnavailableError('Model not loaded')
                if plant_verifier is not None or isinstance(predictor, TrainedTomatoPredictor):
                    check_suitability(data)
                return predictor.predict(data)
        except PredictionUnavailableError as error:
            # Do not leak model paths/errors, substitute a mock, or persist a failed scan.
            raise HTTPException(503, 'Prediction service unavailable. No observation was saved.') from error

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
            raise HTTPException(422, 'Analysis supports tomato plants only. Set crop to tomato or save without analysis.')
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
        return saved

    return app


app = create_app()
