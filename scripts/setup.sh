#!/bin/bash
# Wisdoverse Cell - Setup Script
#
# Usage: ./scripts/setup.sh

set -e

echo "=========================================="
echo "  Wisdoverse Cell - Initial Setup"
echo "=========================================="

# Check Python version
echo ""
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if not exists
echo ""
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env file with your configuration."
else
    echo ".env file already exists."
fi

# Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/milvus

# Check PostgreSQL connection
echo ""
echo "Checking PostgreSQL connection..."
if command -v psql &> /dev/null; then
    echo "PostgreSQL client found."
else
    echo "Warning: PostgreSQL client not found. Make sure PostgreSQL is running."
fi

# Check Redis connection
echo ""
echo "Checking Redis connection..."
if command -v redis-cli &> /dev/null; then
    echo "Redis client found."
else
    echo "Warning: Redis client not found. Make sure Redis is running."
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env file with your configuration"
echo "  2. Create PostgreSQL database: createdb projectcell"
echo "  3. Start Milvus: docker compose -f docker/compose/docker-compose.base.yml -f docker/compose/docker-compose.override.yml up -d milvus"
echo "  4. Run the first agent: python -m agents.requirement-manager.main"
echo ""
