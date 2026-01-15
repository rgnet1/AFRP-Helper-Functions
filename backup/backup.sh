#!/bin/bash
#
# AFRP CRM Helper - Quick Backup Script
# 
# This is a simple wrapper around backup.py for easier use
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}AFRP CRM Helper - Quick Backup${NC}"
echo -e "${BLUE}============================================${NC}"
echo

# Check if running in Docker
if [ -f "/.dockerenv" ] || grep -q 'docker\|lxc' /proc/1/cgroup 2>/dev/null; then
    echo -e "${GREEN}✓ Running inside Docker container${NC}"
    python3 "$SCRIPT_DIR/backup.py" "$@"
else
    echo -e "${YELLOW}Running from host machine${NC}"
    echo
    echo "Choose backup method:"
    echo "  1) Backup from Docker container (recommended)"
    echo "  2) Backup local files directly"
    echo
    read -p "Enter choice [1-2]: " choice
    
    case $choice in
        1)
            echo -e "\n${GREEN}Backing up from Docker container...${NC}\n"
            docker-compose exec -T afrp-helper python3 /app/backup/backup.py "$@"
            
            # Copy backup from container to host if it exists
            if [ $? -eq 0 ]; then
                echo -e "\n${GREEN}✓ Backup created in Docker container${NC}"
                echo -e "${BLUE}Backups are stored in: ./backups/${NC}"
            fi
            ;;
        2)
            echo -e "\n${GREEN}Backing up local files...${NC}\n"
            python3 "$SCRIPT_DIR/backup.py" "$@"
            ;;
        *)
            echo -e "\n${YELLOW}Invalid choice${NC}"
            exit 1
            ;;
    esac
fi

echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Backup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
