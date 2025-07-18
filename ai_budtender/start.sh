#!/bin/bash

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    cp env.example .env
    echo "✅ .env file created. Please edit it if needed."
fi

# Start the project
echo "🚀 Starting AI Budtender..."
docker-compose up --build

echo "🎉 Project started!"
echo "📖 Documentation: http://localhost:8000/api/v1/docs"
echo "🌐 API: http://localhost:8000"
echo "🗄️ Adminer: http://localhost:8080"
echo "📊 Metrics: http://localhost:8000/metrics"
echo "🔴 Redis: redis://localhost:6379" 