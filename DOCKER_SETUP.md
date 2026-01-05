# Docker Setup Guide for FHIR RAG

This guide will help you run the FHIR RAG application using Docker and Docker Compose.

## Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- At least 4GB of RAM available for Docker
- OpenAI API key

## Quick Start

### 1. Setup Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and set your configuration, especially:
- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `SECRET_KEY`: A secure random string (minimum 32 characters)

Generate a secure secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Build and Run

Start all services:

```bash
docker-compose up -d
```

This will:
- Build the backend (Python 3.10.19)
- Build the frontend (Node.js + Nginx)
- Start PostgreSQL database
- Create necessary volumes and networks

### 3. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/api/v1/docs
- **Health Check**: http://localhost:8000/health

### 4. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

## Detailed Commands

### Build Services

```bash
# Build all services
docker-compose build

# Build specific service
docker-compose build backend
docker-compose build frontend

# Build without cache (for fresh build)
docker-compose build --no-cache
```

### Start/Stop Services

```bash
# Start all services in background
docker-compose up -d

# Start specific service
docker-compose up -d backend

# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes database data)
docker-compose down -v
```

### Service Management

```bash
# Restart a service
docker-compose restart backend

# View running containers
docker-compose ps

# Execute command in container
docker-compose exec backend bash
docker-compose exec postgres psql -U admin -d Spice_BD
```

### Database Management

```bash
# Access PostgreSQL
docker-compose exec postgres psql -U admin -d Spice_BD

# Backup database
docker-compose exec postgres pg_dump -U admin Spice_BD > backup.sql

# Restore database
cat backup.sql | docker-compose exec -T postgres psql -U admin -d Spice_BD

# View database logs
docker-compose logs postgres
```

## Development Workflow

### Hot Reload (Development Mode)

For development with hot reload:

1. **Backend**: Uncomment the volume mount in `docker-compose.yml` (already configured)
2. **Frontend**: Use development mode:

```bash
# Stop production frontend
docker-compose stop frontend

# Run frontend in dev mode locally
cd frontend
npm install
npm run dev
```

### Debugging

```bash
# Check service health
docker-compose ps

# View container resource usage
docker stats

# Inspect a container
docker inspect fhir_rag_backend

# View backend logs with timestamps
docker-compose logs -f --timestamps backend
```

## Production Deployment

### Security Checklist

- [ ] Change `SECRET_KEY` to a strong random value
- [ ] Update database credentials
- [ ] Set `DEBUG=false`
- [ ] Configure proper CORS origins
- [ ] Use environment-specific `.env` files
- [ ] Enable HTTPS/SSL
- [ ] Set up proper backup strategy
- [ ] Configure firewall rules

### Production Configuration

Create a `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  backend:
    environment:
      DEBUG: "false"
      LOG_LEVEL: WARNING
    restart: always
    
  frontend:
    restart: always
    
  postgres:
    restart: always
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
```

Run with:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs backend

# Rebuild without cache
docker-compose build --no-cache backend
docker-compose up -d backend
```

### Database Connection Issues

```bash
# Check if PostgreSQL is ready
docker-compose exec postgres pg_isready -U admin

# Restart database
docker-compose restart postgres

# Check database logs
docker-compose logs postgres
```

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000
sudo lsof -i :8000

# Kill process or change port in docker-compose.yml
```

### Out of Disk Space

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove everything (WARNING: deletes all data)
docker system prune -a --volumes
```

### Backend API Not Responding

```bash
# Check if backend is healthy
curl http://localhost:8000/health

# Check logs
docker-compose logs backend

# Restart backend
docker-compose restart backend
```

## Model Files

If you have local embedding models (like bge-m3), ensure they are:

1. Located in `backend/models/bge-m3/`
2. Mounted as a volume in docker-compose.yml
3. Accessible with proper permissions

## Data Persistence

Data is persisted in Docker volumes:

- **postgres_data**: Database data
- **backend/data**: Vector indexes and feedback logs
- **backend/logs**: Application logs

Backup these regularly in production!

## Scaling

To scale services:

```bash
# Scale backend to 3 instances
docker-compose up -d --scale backend=3
```

Note: You'll need to configure a load balancer (like Nginx) for multiple backend instances.

## Clean Up

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (deletes data)
docker-compose down -v

# Remove images
docker rmi fhir_rag_backend fhir_rag_frontend

# Complete cleanup
docker system prune -a --volumes
```

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Verify environment variables in `.env`
3. Ensure all required models/data files are present
4. Check Docker resources (CPU, Memory, Disk)

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ :3000
       ▼
┌─────────────┐
│  Frontend   │ (Nginx)
│  Container  │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌─────────────┐
│   Backend   │─────▶│  PostgreSQL │
│  Container  │:8000 │  Container  │
└─────────────┘      └─────────────┘
  (Python 3.10.19)      (Port 5432)
```

All containers communicate over the `fhir_rag_network` Docker network.
