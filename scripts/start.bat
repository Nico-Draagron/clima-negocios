@echo off
echo 🚀 Iniciando Clima e Negocios...

if not exist .env (
    copy .env.example .env
    echo ✅ Arquivo .env criado
)

echo 🐳 Iniciando containers...
docker-compose up -d

echo ✅ Pronto!
echo Frontend: http://localhost:3000
echo API: http://localhost:8000/docs
pause
