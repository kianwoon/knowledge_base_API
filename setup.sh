#!/bin/bash
# Script to set up the Mail Analysis API project

# Create virtual environment
echo "Creating virtual environment..."
python -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    
    # Generate encryption key
    echo "Generating encryption key..."
    ENCRYPTION_KEY=$(python -c "import base64; import os; print(base64.b64encode(os.urandom(32)).decode())")
    
    # Update .env file with encryption key
    sed -i '' "s/your_encryption_key_here/$ENCRYPTION_KEY/g" .env
    
    echo "Please edit .env file to set your OpenAI API key."
fi

# Create config directory if it doesn't exist
if [ ! -d config ]; then
    echo "Creating config directory..."
    mkdir -p config
fi

# Create settings.yaml file if it doesn't exist
if [ ! -f config/settings.yaml ]; then
    echo "Creating settings.yaml file..."
    cp config/settings.example.yaml config/settings.yaml
fi

# Create logs directory if it doesn't exist
if [ ! -d logs ]; then
    echo "Creating logs directory..."
    mkdir -p logs
fi

echo "Setup completed successfully!"
echo "Please make sure Redis is running before starting the application."
echo "To start the application, run: ./run_local.sh"
