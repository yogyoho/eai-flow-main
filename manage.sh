#!/bin/bash
# EAI Flow Docker Management Script
# Manages both core services (gateway, langgraph, frontend, nginx) and business services

set -e

cd "$(dirname "$0")"

show_help() {
    echo "EAI Flow Docker Management Script"
    echo ""
    echo "Usage: $0 {start|stop|restart|build|logs|ps|clean}"
    echo ""
    echo "Commands:"
    echo "  start       - Start all services (build if needed)"
    echo "  stop        - Stop all services"
    echo "  restart     - Restart all services"
    echo "  build       - Build images without cache"
    echo "  build-cache - Build images with cache"
    echo "  logs [svc]  - View logs (optional: specific service name)"
    echo "  ps          - Show running containers"
    echo "  clean       - Remove containers and unused images"
    echo ""
    echo "Services:"
    echo "  Core:       nginx, frontend, gateway, langgraph"
    echo "  Business:   procurement-backend, procurement-frontend"
    echo "              asset-backend, asset-frontend"
    echo "              project-backend, project-frontend"
    echo ""
    echo "Ports:"
    echo "  Main:       http://localhost:4026 (nginx)"
    echo "  Gateway:    http://localhost:4001"
    echo "  LangGraph:  http://localhost:4024"
    echo "  Frontend:   http://localhost:4000"
    echo "  Procurement:http://localhost:3004"
    echo "  Asset:      http://localhost:3005"
    echo "  Project:    http://localhost:3006"
}

case "$1" in
  start|up)
    echo "Starting EAI Flow Docker services..."
    docker compose -f docker/docker-compose-dev.yaml up -d
    echo ""
    echo "Services started!"
    echo "Main access: http://localhost:4026"
    ;;
  stop|down)
    echo "Stopping EAI Flow Docker services..."
    docker compose -f docker/docker-compose-dev.yaml down
    ;;
  restart)
    echo "Restarting EAI Flow Docker services..."
    docker compose -f docker/docker-compose-dev.yaml restart
    ;;
  build)
    echo "Building EAI Flow Docker images (no cache)..."
    docker compose -f docker/docker-compose-dev.yaml build --no-cache
    ;;
  build-cache)
    echo "Building EAI Flow Docker images (with cache)..."
    docker compose -f docker/docker-compose-dev.yaml build
    ;;
  logs)
    docker compose -f docker/docker-compose-dev.yaml logs -f "${2:-}"
    ;;
  ps)
    docker compose -f docker/docker-compose-dev.yaml ps
    ;;
  clean)
    echo "Cleaning up Docker resources..."
    docker compose -f docker/docker-compose-dev.yaml down -v --remove-orphans
    docker system prune -f
    ;;
  help|--help|-h)
    show_help
    exit 0
    ;;
  *)
    echo "Unknown command: $1"
    show_help
    exit 1
    ;;
esac
