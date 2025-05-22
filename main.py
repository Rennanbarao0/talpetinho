from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field, validator
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

MONGO_DETAILS = os.getenv("MONGO_CONECTION")

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.users_db
user_collection = database.get_collection("users")

app = FastAPI()

class User(BaseModel):
    full_name: str = Field(..., min_length=3)
    birth_date: str = Field(..., description="Data de nascimento no formato DD/MM/YYYY")
    email: EmailStr
    phone: str = Field(..., min_length=8)
    accept_terms: bool = Field(..., description="Deve ser True para aceitar os termos de uso")

    @validator('birth_date')
    def validar_data(cls, v):
        try:
            data_nascimento = datetime.strptime(v, "%d/%m/%Y")
        except ValueError:
            raise ValueError('A data deve estar no formato DD/MM/YYYY')

        hoje = datetime.today()
        idade = hoje.year - data_nascimento.year - (
            (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
        )

        if idade < 16:
            raise ValueError('É necessário ter no mínimo 16 anos para se cadastrar.')

        return v

@app.post("/cadastrar")
async def cadastrar_usuario(user: User):
    if not user.accept_terms:
        raise HTTPException(status_code=400, detail="É necessário aceitar os termos de uso para se cadastrar.")

    user_exist = await user_collection.find_one({"email": user.email})
    if user_exist:
        raise HTTPException(status_code=409, detail="Email já cadastrado.")
    
    user_dict = user.dict()
    result = await user_collection.insert_one(user_dict)
    
    return {
        "id": str(result.inserted_id),
        "message": "Usuário cadastrado com sucesso."
    }
