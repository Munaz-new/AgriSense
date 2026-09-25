from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .database import connect, initialize
from .prediction import MockPredictor, Prediction, PredictionUnavailableError, Predictor
from .image_validation import (MAX_IMAGE_BYTES, PlantImageValidator, TechnicalPlantImageValidator,
                               ValidationResult, image_extension)

ROOT = Path(__file__).resolve().parents[2]


class PlantInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)


class Plant(PlantInput):
    id: str
    created_at: str


class Observation(Prediction):
    id: str
    plant_id: str
    image_path: str
    created_at: str
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

    app = FastAPI(title="AgriSense Phase 2A", lifespan=lifespan,
                  description="Local MVP. Predictions are synthetic development-only results.")
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
        return {"status": "ok", "prediction_mode": "development-only mock" if isinstance(predictor, MockPredictor) else "custom predictor", "is_mock": isinstance(predictor, MockPredictor)}

    @app.post("/plants", response_model=Plant, status_code=201)
    def add_plant(body: PlantInput):
        plant = {"id": str(uuid4()), "name": body.name, "created_at": now()}
        with connect(database_path) as db:
            db.execute("INSERT INTO plants VALUES (:id, :name, :created_at)", plant)
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
                "SELECT * FROM observations WHERE plant_id = ? ORDER BY created_at ASC, id ASC", (plant_id,))]

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
                           humidity=humidity, soil_type=soil_type, soil_condition=soil_condition)
        target = upload_dir / filename
        try:
            target.write_bytes(data)
            with connect(database_path) as db:
                db.execute("""INSERT INTO observations VALUES
                    (:id, :plant_id, :image_path, :created_at, :disease, :severity, :confidence,
                     :predictor, :is_mock, :temperature, :humidity, :soil_type, :soil_condition)""", observation)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return observation

    return app


app = create_app()
