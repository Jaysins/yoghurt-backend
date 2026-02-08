#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
APP_NAME="Yoghurt"
CONTAINER_NAME="yoghurt_backend"
COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ------------------ Helpers ------------------

print_header() {
    echo ""
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_info()    { echo -e "${BLUE}ℹ $1${NC}"; }

# ------------------ Checks ------------------

check_requirements() {
    print_header "Checking Requirements"

    [ -f .env ] || { print_error ".env file not found"; exit 1; }
    [ -f Dockerfile ] || { print_error "Dockerfile not found"; exit 1; }
    [ -f "$COMPOSE_FILE" ] || { print_error "$COMPOSE_FILE not found"; exit 1; }

    print_success "All required files found"
}

load_env() {
    [ -f .env ] && export $(grep -v '^#' .env | xargs)
}

check_shared_services() {
    print_header "Checking Shared Services"

    sudo docker ps | grep -q shared_postgres \
        || { print_error "Shared Postgres not running"; exit 1; }
    print_success "Shared Postgres is running"

    sudo docker ps | grep -q shared_redis \
        && print_success "Shared Redis is running" \
        || print_warning "Shared Redis not running"
}

# ------------------ Backup ------------------

backup_database() {
    print_header "Backing Up Database"

    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/yoghurt_${TIMESTAMP}.sql"

    print_info "Creating backup..."
    sudo docker exec shared_postgres \
        pg_dump -U ${POSTGRES_USER:-postgres} ${POSTGRES_DB:-yoghurt} \
        > "$BACKUP_FILE"

    gzip "$BACKUP_FILE"
    print_success "Backup saved: ${BACKUP_FILE}.gz"

    ls -t $BACKUP_DIR/*.sql.gz | tail -n +6 | xargs -r rm
}

# ------------------ Deploy ------------------

pull_code() {
    print_header "Pulling Latest Code"
    git pull origin "$(git rev-parse --abbrev-ref HEAD)"
}

stop_service() {
    print_header "Stopping Service"
    sudo docker compose -f $COMPOSE_FILE down
}

build_image() {
    print_header "Building Image"
    sudo docker compose -f $COMPOSE_FILE build --no-cache
    sudo docker image prune -f
}

run_migrations() {
    print_header "Running Migrations"

    sudo docker compose -f $COMPOSE_FILE run --rm yoghurt-backend \
        alembic upgrade head \
        || print_warning "No migrations run"
}

start_service() {
    print_header "Starting Service"
    sudo docker compose -f $COMPOSE_FILE up -d
    sleep 5

    sudo docker ps | grep -q "$CONTAINER_NAME" \
        && print_success "Service started" \
        || { print_error "Service failed"; exit 1; }
}

show_info() {
    print_header "Deployment Complete"

    echo -e "${GREEN}✨ ${APP_NAME} deployed successfully!${NC}"
    echo ""
    echo -e "Service URL: ${GREEN}http://localhost:5000${NC}"
    echo -e "Container:   ${BLUE}${CONTAINER_NAME}${NC}"
    echo ""

    sudo docker compose -f $COMPOSE_FILE ps
}

# ------------------ Main ------------------

main() {
    print_header "${APP_NAME} Deployment"

    load_env
    check_requirements
    check_shared_services
    pull_code
    build_image
    stop_service
    run_migrations
    start_service
    show_info

    print_success "Deployment completed at $(date)"
}

trap 'echo -e "\n${RED}Deployment interrupted${NC}"; exit 130' INT
main "$@"
