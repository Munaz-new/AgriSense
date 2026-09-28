from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .database import connect, initialize, insert_observation
from .records import RequestConflict, save_record
from .progression import progression
from .prediction import MockPredictor, Prediction, PredictionUnavailableError, Predictor
from .image_validation import (MAX_IMAGE_BYTES, PlantImageValidator, TechnicalPlantImageValidator,
                               ValidationResult, image_extension)

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
    temperature: float
    humidity: float
    soil_type: str
    soil_condition: Literal["Dry", "Normal", "Wet"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def read_image(upload: UploadFile) -> bytes:
    try:
        return await upload.read(MAX_IMAGE_BYTES + 1)
    finally:
        await upload.close()


def create_app(database_path: Path | None = None, upload_dir: Path | None = None,
               predictor: Predictor | None = None,
               validator: PlantImageValidator | None = None) -> FastAPI:
    database_path = database_path or Path(os.getenv("AGRISENSE_DB_PATH", ROOT / "database/agrisense.db"))
    upload_dir = upload_dir or Path(os.getenv("AGRISENSE_UPLOAD_DIR", ROOT / "backend/uploads"))
    predictor = predictor or MockPredictor()
    validator = validator or TechnicalPlantImageValidator()
    upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(database_path)
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
        return {"status": "ok", "prediction_mode": "development-only mock" if isinstance(predictor, MockPredictor) else "custom predictor", "is_mock": isinstance(predictor, MockPredictor),
                "capabilities": {"record_only": True, "validated_analysis": False,
                                 "severity_measurement": False, "health_progression": False},
                "analysis_message": "Validated disease analysis is not enabled. Observations can be saved without analysis."}

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

    def predict_image(data: bytes) -> Prediction:
        try:
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
        return predict_image(data)

    @app.post('/plants/{plant_id}/records', response_model=Observation, status_code=201)
    async def add_record(
        plant_id: str, response: Response,
        image: Annotated[UploadFile, File()],
        request_id: Annotated[str, Form(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')],
        temperature: Annotated[float, Form(ge=-50, le=70, allow_inf_nan=False)],
        humidity: Annotated[float, Form(ge=0, le=100, allow_inf_nan=False)],
        soil_type: Annotated[str, Form(min_length=1, max_length=100)],
        soil_condition: Annotated[Literal['Dry', 'Normal', 'Wet'], Form()],
        observed_at: Annotated[datetime | None, Form()] = None,
        tracking_ref: Annotated[str | None, Form(max_length=100)] = None,
        notes: Annotated[str | None, Form(max_length=2000)] = None,
    ):
        require_plant(plant_id)
        soil_type = soil_type.strip()
        if not soil_type:
            raise HTTPException(422, 'Soil type cannot be blank.')
        if observed_at is not None and (observed_at.tzinfo is None or observed_at > datetime.now(timezone.utc)):
            raise HTTPException(422, 'Observation time must include a timezone and must not be in the future.')
        fields = dict(request_id=request_id, temperature=temperature, humidity=humidity,
                      soil_type=soil_type, soil_condition=soil_condition,
                      observed_at=observed_at.astimezone(timezone.utc).isoformat() if observed_at else None,
                      tracking_ref=tracking_ref.strip() or None if tracking_ref else None,
                      notes=notes.strip() or None if notes else None)
        data, _ = await validated_image(image)
        try:
            saved, replay = save_record(database_path, upload_dir, plant_id, data,
                                        image_extension(data), fields, now())
        except RequestConflict as error:
            raise HTTPException(409, str(error)) from error
        if replay:
            response.status_code = 200
        return saved

    @app.post("/plants/{plant_id}/observations", response_model=Observation, status_code=201)
    async def add_observation(
        plant_id: str,
        image: Annotated[UploadFile, File()],
        temperature: Annotated[float, Form(ge=-50, le=70, allow_inf_nan=False)],
        humidity: Annotated[float, Form(ge=0, le=100, allow_inf_nan=False)],
        soil_type: Annotated[str, Form(min_length=1, max_length=100)],
        soil_condition: Annotated[Literal["Dry", "Normal", "Wet"], Form()],
    ):
        require_plant(plant_id)
        soil_type = soil_type.strip()
        if not soil_type:
            raise HTTPException(422, "Soil type cannot be blank.")
        data, _ = await validated_image(image)
        extension = image_extension(data)
        # Environmental context deliberately never crosses the predictor boundary.
        result = predict_image(data)
        observation_id = str(uuid4())
        filename = f"{observation_id}.{extension}"
        observation = dict(id=observation_id, plant_id=plant_id, image_path=f"/uploads/{filename}",
                           created_at=now(), **result.model_dump(), temperature=temperature,
                           humidity=humidity, soil_type=soil_type, soil_condition=soil_condition,
                           analysis_status='completed', image_sha256=sha256(data).hexdigest(),
                           checkpoint_id=getattr(predictor, 'checkpoint_id', None))
        target = upload_dir / filename
        try:
            target.write_bytes(data)
            with connect(database_path) as db:
                insert_observation(db, observation)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return observation

    return app


app = create_app()
