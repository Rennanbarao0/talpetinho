from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, validator
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime, date
import os
import httpx

load_dotenv()

MONGO_DETAILS = os.getenv("MONGO_CONECTION")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.users_db
user_collection = database.get_collection("users")

app = FastAPI()

origins = [
    "http://localhost:9000",
    "http://127.0.0.1:9000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class User(BaseModel):
    full_name: str = Field(..., min_length=3)
    birth_date: date = Field(..., description="Data de nascimento no formato DD/MM/YYYY")
    email: EmailStr
    phone: str = Field(..., min_length=8)
    accept_terms: bool = Field(..., description="Deve ser True para aceitar os termos de uso")

    @validator('birth_date', pre=True)
    def parse_birth_date(cls, v):
        if isinstance(v, date):
            return v
        try:
            return datetime.strptime(v, "%d/%m/%Y").date()
        except Exception:
            raise ValueError("A data deve estar no formato DD/MM/YYYY")

    @validator('birth_date')
    def validar_idade(cls, v):
        hoje = date.today()
        idade = hoje.year - v.year - ((hoje.month, hoje.day) < (v.month, v.day))
        if idade < 16:
            raise ValueError('É necessário ter no mínimo 16 anos para se cadastrar.')
        return v

def calcular_signo(birth_date: date) -> str:
    signos = [
        ((3, 21), (4, 19), "Áries"),
        ((4, 20), (5, 20), "Touro"),
        ((5, 21), (6, 20), "Gêmeos"),
        ((6, 21), (7, 22), "Câncer"),
        ((7, 23), (8, 22), "Leão"),
        ((8, 23), (9, 22), "Virgem"),
        ((9, 23), (10, 22), "Libra"),
        ((10, 23), (11, 21), "Escorpião"),
        ((11, 22), (12, 21), "Sagitário"),
        ((12, 22), (12, 31), "Capricórnio"),
        ((1, 1), (1, 19), "Capricórnio"),
        ((1, 20), (2, 18), "Aquário"),
        ((2, 19), (3, 20), "Peixes"),
    ]

    for start, end, signo in signos:
        start_month, start_day = start
        end_month, end_day = end

        start_date = date(birth_date.year, start_month, start_day)
        end_date = date(birth_date.year, end_month, end_day)

        if end_date < start_date:
            if birth_date >= start_date or birth_date <= end_date:
                return signo
        else:
            if start_date <= birth_date <= end_date:
                return signo

    return "Signo não encontrado"

@app.post("/cadastrar")
async def cadastrar_usuario(user: User):
    if not user.accept_terms:
        raise HTTPException(status_code=400, detail="É necessário aceitar os termos de uso para se cadastrar.")

    user_exist = await user_collection.find_one({"email": user.email})
    if user_exist:
        raise HTTPException(status_code=409, detail="Email já cadastrado.")

    signo = calcular_signo(user.birth_date)

    user_dict = user.dict()

    # Convertendo birth_date para datetime.datetime para MongoDB
    if isinstance(user_dict.get('birth_date'), date) and not isinstance(user_dict.get('birth_date'), datetime):
        user_dict['birth_date'] = datetime.combine(user_dict['birth_date'], datetime.min.time())

    user_dict["zodiac_sign"] = signo

    result = await user_collection.insert_one(user_dict)

    async with httpx.AsyncClient() as client_http:
        try:
            response = await client_http.post(
                N8N_WEBHOOK_URL,
                json={
                    "nome": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "birth_date": user.birth_date.strftime("%d/%m/%Y"),
                    "zodiac_sign": signo
                },
                timeout=10.0
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            print(f"Erro ao chamar webhook n8n: {e}")

    return {
        "id": str(result.inserted_id),
        "message": "Usuário cadastrado com sucesso.",
        "zodiac_sign": signo
    }

class ChatIDUpdate(BaseModel):
    email: EmailStr
    chat_id: int

@app.patch("/atualizar_chat_id")
async def atualizar_chat_id(data: ChatIDUpdate = Body(...)):
    user = await user_collection.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    update_result = await user_collection.update_one(
        {"email": data.email},
        {"$set": {"chat_id": data.chat_id}}
    )

    if update_result.modified_count == 1:
        return {"message": "chat_id atualizado com sucesso"}
    else:
        raise HTTPException(status_code=400, detail="Não foi possível atualizar o chat_id")

@app.get("/buscar_usuario")
async def buscar_usuario(email: EmailStr = Query(..., description="Email do usuário para busca")):
    user = await user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user["id"] = str(user["_id"])
    del user["_id"]

    return user
