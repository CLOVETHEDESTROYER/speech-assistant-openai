#!/bin/bash

# Production deployment script
echo "Deploying to DigitalOcean droplet..."

# Variables
DROPLET_IP="164.92.71.74"
APP_DIR="/var/www/AiFriendChatBeta"  # Updated path
SYSTEMD_SERVICE="aifriendchatbeta"    # Updated service name

# Deploy to production
echo "Deploying to $DROPLET_IP..."

# Copy files to server
rsync -avz --exclude 'venv' \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env.development' \
    --exclude 'local.db' \
    ./ root@$DROPLET_IP:$APP_DIR/

# SSH into the server and run setup commands
ssh root@$DROPLET_IP << 'EOF'
    cd /var/www/AiFriendChatBeta

    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi

    # Activate virtual environment and install dependencies
    source venv/bin/activate
    pip install -r requirements.txt
    pip install gunicorn

    # Ensure the service is properly configured
    sudo systemctl daemon-reload
    sudo systemctl restart aifriendchatbeta
    sudo systemctl status aifriendchatbeta

    # Check nginx configuration and restart
    sudo nginx -t && sudo systemctl restart nginx

    echo "Deployment completed!"
EOF
