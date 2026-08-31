#!/bin/bash
set -e

CONFIG_FILE="topology.conf"

# Verify the configuration file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "[!] Configuration file $CONFIG_FILE not found."
  exit 1
fi

declare -A CONNECTION_SCHEMA

# Read Configuration File
while IFS='=' read -r key value || [[ -n "$key" ]]; do
  # Ignorer les lignes vides et les commentaires
  [[ -z "$key" || "$key" =~ ^# ]] && continue
  CONNECTION_SCHEMA["$key"]="$value"
done < "$CONFIG_FILE"

# Fetch the number of instances by finding the highest key
if [[ -z "$NUM_INSTANCES" ]]; then
  NUM_INSTANCES=0
  for k in "${!CONNECTION_SCHEMA[@]}"; do
    (( k > NUM_INSTANCES )) && NUM_INSTANCES=$k
  done
fi
echo "Number of instances: $NUM_INSTANCES"

echo -e "[+] CONNECTION_SCHEMA loaded from config"
for key in $(printf "%s\n" "${!CONNECTION_SCHEMA[@]}" | sort -n); do
  echo "Instance $key ↔️  ${CONNECTION_SCHEMA[$key]}"
done


# Verify internal status for the last two instances
INTERNAL_LAST_TWO=true
for arg in "$@"; do
    if [ "$arg" == "-no-internal" ]; then
        INTERNAL_LAST_TWO=false
        break
    fi
done

echo "Internal status for the last two instances: $INTERNAL_LAST_TWO"

MISP_DOCKER_URL="https://github.com/MISP/misp-docker.git"
MISP_DOCKER_DIR="misp-docker"

declare -A HOSTS      # Stores host addresses for each instance
declare -A AUTHS      # Stores admin API keys for each instance
declare -A AUTHS_ORG  # Stores org admin API keys for each instance
declare -A ORG_UUIDS  # Stores UUIDs for each organisation

# [2] Environment preparation

# Install Docker if not present
if ! command -v docker &> /dev/null; then
  echo "[+] Installing Docker..."
  sudo apt install -y docker.io
  sudo systemctl enable --now docker
fi

# Fetch the compose command depending on the installed version
if command -v docker-compose &> /dev/null; then
  COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
  COMPOSE_CMD="docker compose"
else
  echo "[!] Docker Compose is not installed. Please install Docker Compose."
  exit 1
fi

echo "[+] Using command: $COMPOSE_CMD"

# Remove old repository if exists and clone fresh
if [ -d "$MISP_DOCKER_DIR" ]; then
  echo "[*] Removing old repository..."
  rm -rf "$MISP_DOCKER_DIR"
fi
git clone "$MISP_DOCKER_URL"
cd "$MISP_DOCKER_DIR" || exit 1

# Create directories for each instance
for i in $(seq 1 "$NUM_INSTANCES"); do
  mkdir -p "instance-$i/instance-config"
  mkdir -p "instance-$i/instance-log"
  mkdir -p "instance-$i/instance-files"
  mkdir -p "instance-$i/instance-ssl"
  mkdir -p "instance-$i/instance-gnupg"
done

# [3] Generate docker-compose.yml
echo "[+] Generating docker-compose.yml..."

cat > docker-compose.yml <<EOF
services:
  mail:
    image: ixdotai/smtp
    environment:
      - "SMARTHOST_ADDRESS=\${SMARTHOST_ADDRESS}"
      - "SMARTHOST_PORT=\${SMARTHOST_PORT}"
      - "SMARTHOST_USER=\${SMARTHOST_USER}"
      - "SMARTHOST_PASSWORD=\${SMARTHOST_PASSWORD}"
      - "SMARTHOST_ALIASES=\${SMARTHOST_ALIASES}"

  redis:
    image: valkey/valkey:7.2
    command: "--requirepass '\${REDIS_PASSWORD:-redispassword}'"
    healthcheck:
      test: "valkey-cli -a '\${REDIS_PASSWORD:-redispassword}' -p \${REDIS_PORT:-6379} ping | grep -q PONG || exit 1"
      interval: 2s
      timeout: 1s
      retries: 3
      start_period: 5s
      start_interval: 5s
EOF

# Add database and MISP service definitions for each instance
for i in $(seq 1 "$NUM_INSTANCES"); do
cat >> docker-compose.yml <<EOF

  db_$i:
    image: mariadb:10.11
    restart: always
    environment:
      - "MYSQL_USER=\${MYSQL_USER:-misp}"
      - "MYSQL_PASSWORD=\${MYSQL_PASSWORD:-example}"
      - "MYSQL_ROOT_PASSWORD=\${MYSQL_ROOT_PASSWORD:-password}"
      - "MYSQL_DATABASE=\${MYSQL_DATABASE:-misp_$i}"
    command: "\
      --innodb-buffer-pool-size=\${INNODB_BUFFER_POOL_SIZE:-2048M} \
      --innodb-change-buffering=\${INNODB_CHANGE_BUFFERING:-none} \
      --innodb-io-capacity=\${INNODB_IO_CAPACITY:-1000} \
      --innodb-io-capacity-max=\${INNODB_IO_CAPACITY_MAX:-2000} \
      --innodb-log-file-size=\${INNODB_LOG_FILE_SIZE:-600M} \
      --innodb-read-io-threads=\${INNODB_READ_IO_THREADS:-16} \
      --innodb-stats-persistent=\${INNODB_STATS_PERSISTENT:-ON} \
      --innodb-write-io-threads=\${INNODB_WRITE_IO_THREADS:-4}"
    volumes:
      - mysql_data_$i:/var/lib/mysql
    cap_add:
      - SYS_NICE
    healthcheck:
      test: mysqladmin --user=\$\$MYSQL_USER --password=\$\$MYSQL_PASSWORD status
      interval: 2s
      timeout: 1s
      retries: 3
      start_period: 30s
      start_interval: 5s

  misp_$i:
    image: ghcr.io/misp/misp-docker/misp-core:\${CORE_RUNNING_TAG:-latest}
    build:
      context: core/.
      args:
        - CORE_TAG=\${CORE_TAG:?Missing .env file, see README.md for instructions}
        - CORE_COMMIT=\${CORE_COMMIT}
        - CORE_FLAVOR=\${CORE_FLAVOR:-full}
        - PHP_VER=\${PHP_VER:?Missing .env file, see README.md for instructions}
        - PYPI_REDIS_VERSION=\${PYPI_REDIS_VERSION}
        - PYPI_LIEF_VERSION=\${PYPI_LIEF_VERSION}
        - PYPI_PYDEEP2_VERSION=\${PYPI_PYDEEP2_VERSION}
        - PYPI_PYTHON_MAGIC_VERSION=\${PYPI_PYTHON_MAGIC_VERSION}
        - PYPI_MISP_LIB_STIX2_VERSION=\${PYPI_MISP_LIB_STIX2_VERSION}
        - PYPI_MAEC_VERSION=\${PYPI_MAEC_VERSION}
        - PYPI_MIXBOX_VERSION=\${PYPI_MIXBOX_VERSION}
        - PYPI_CYBOX_VERSION=\${PYPI_CYBOX_VERSION}
        - PYPI_PYMISP_VERSION=\${PYPI_PYMISP_VERSION}
        - PYPI_MISP_STIX_VERSION=\${PYPI_MISP_STIX_VERSION}
        - PYPI_SETUPTOOLS=\${PYPI_SETUPTOOLS}
        - PYPI_SUPERVISOR=\${PYPI_SUPERVISOR}
    depends_on:
      redis:
        condition: service_healthy
      db_$i:
        condition: service_healthy
    healthcheck:
      test: curl -ks \${BASE_URL:-http://localhost}/users/heartbeat > /dev/null || exit 1
      interval: 2s
      timeout: 1s
      retries: 3
      start_period: 30s
      start_interval: 30s
    ports:
      - "808$i:80"
      - "844$i:443"
    volumes:
      - "./instance-$i/instance-config/:/var/www/MISP/app/Config/"
      - "./instance-$i/instance-log/:/var/www/MISP/app/tmp/logs/"
      - "./instance-$i/instance-files/:/var/www/MISP/app/files/"
      - "./instance-$i/instance-ssl/:/etc/nginx/certs/"
      - "./instance-$i/instance-gnupg/:/var/www/MISP/.gnupg/"
    environment:
      - "BASE_URL=http://localhost:808$i"
      - "CRON_USER_ID=\${CRON_USER_ID}"
      - "CRON_PULLALL=\${CRON_PULLALL}"
      - "CRON_PUSHALL=\${CRON_PUSHALL}"
      - "DISABLE_IPV6=\${DISABLE_IPV6}"
      - "DISABLE_SSL_REDIRECT=\${DISABLE_SSL_REDIRECT}"
      - "ENABLE_DB_SETTINGS=\${ENABLE_DB_SETTINGS}"
      - "ENABLE_BACKGROUND_UPDATES=\${ENABLE_BACKGROUND_UPDATES}"
      - "ENCRYPTION_KEY=\${ENCRYPTION_KEY}"
      - "DISABLE_CA_REFRESH=\${DISABLE_CA_REFRESH}"
      # MySQL settings
      - "MYSQL_HOST=\${MYSQL_HOST:-db_$i}"
      - "MYSQL_PORT=\${MYSQL_PORT:-3306}"
      - "MYSQL_USER=\${MYSQL_USER:-misp}"
      - "MYSQL_PASSWORD=\${MYSQL_PASSWORD:-example}"
      - "MYSQL_DATABASE=\${MYSQL_DATABASE:-misp_$i}"
      # Redis settings
      - "REDIS_HOST=\${REDIS_HOST:-redis}"
      - "REDIS_PORT=\${REDIS_PORT:-6379}"
      - "REDIS_PASSWORD=\${REDIS_PASSWORD:-redispassword}"
      # Debug setting 
      - "DEBUG=\${DEBUG}"
EOF
done

# Define Docker volumes for each instance
echo -e "\nvolumes:" >> docker-compose.yml
for i in $(seq 1 "$NUM_INSTANCES"); do
  echo "  mysql_data_$i:" >> docker-compose.yml
done

echo "[✓] docker-compose.yml generated."

# Prepare .env file for Docker Compose
cp template.env .env
TMP_ENV=$(mktemp)
sed 's/^# *\(DISABLE_SSL_REDIRECT=true\)/\1/' .env > "$TMP_ENV"
mv "$TMP_ENV" .env

echo "[+] Pulling Docker images..."
$COMPOSE_CMD pull

echo "[+] Starting Docker services..."
$COMPOSE_CMD up -d

echo "[✓] Containers started. Processing initialization of each MISP instance (could take a few minutes depending on your system)"

# Wait for each MISP container to finish initialization
for i in $(seq 1 "$NUM_INSTANCES"); do
  container_name="misp-docker-misp_${i}-1"
  echo -n "Waiting for full initialization of $container_name... "
  while true; do
    if docker logs "$container_name" 2>&1 | grep -q "INIT | Done"; then
      echo "OK"
      break
    else
      sleep 5
    fi
  done
done

# --- [4] API key reading and export ---
# Reset admin API keys automatically for each instance
for i in $(seq 1 $NUM_INSTANCES); do
  HOSTS[$i]="localhost:808$i"
  echo "🔑 Reset admin credentials for instance $i..."

  API_KEY=$(docker exec -i "misp-docker-misp_${i}-1" \
    bash -c "cd /var/www/MISP && sudo -u www-data /var/www/MISP/app/Console/cake user change_authkey 1" \
    | grep 'new key created' | awk -F': ' '{print $2}')

  echo "Instance $i API Key: [REDACTED]"
  AUTHS[$i]=$API_KEY
  export HOST_$i="${HOSTS[$i]}"
  export AUTH_$i="${AUTHS[$i]}"
done

sleep 30

# --- [5] Synchronization functions ---

# generate_uuids: Generate a UUID for each organisation
generate_uuids() {
  for i in "${!HOSTS[@]}"; do
    ORG_UUIDS[$i]=$(uuidgen)
  done
}

# get_org_id_on_instance: Retrieve the organisation ID for a given org on a specific instance
# Arguments:
#   $1: Instance index
#   $2: Organisation index
get_org_id_on_instance() {
  local instance_index="$1"
  local org_index="$2"

  curl -s -X GET "http://${HOSTS[$instance_index]}/organisations/index.json" \
    -H "Authorization: ${AUTHS[$instance_index]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    | jq -r ".[] | select(.Organisation.name==\"ORG_$org_index\") | .Organisation.id"
}

# create_all_orgs_on_instance: Create all organisations on a given instance
# Arguments:
#   $1: Instance index
create_all_orgs_on_instance() {
  local id="$1"
  echo "[*] Creating all organisations on instance $id"

  for org_id in "${!ORG_UUIDS[@]}"; do
    local payload=$(jq -n \
      --arg name "ORG_$org_id" \
      --arg uuid "${ORG_UUIDS[$org_id]}" \
      --arg desc "Owner organisation of instance $org_id" \
      '{name: $name, uuid: $uuid, description: $desc}')

    curl -s -X POST "http://${HOSTS[$id]}/admin/organisations/add" \
      -H "Authorization: ${AUTHS[$id]}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d "$payload" > /dev/null
  done
}

# set_host_org: Set the host organisation for a given instance and create an admin user for it
# Arguments:
#   $1: Instance index
set_host_org() {
  local id="$1"
  local org_id

  if [ $INTERNAL_LAST_TWO ] && [ "$id" -eq "$NUM_INSTANCES" ]; then
    echo "[+] Getting ID of ORG_$((id-1)) on instance $id"
    org_id=$(curl -s -X GET "http://${HOSTS[$id]}/organisations/index.json" \
      -H "Authorization: ${AUTHS[$id]}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      | jq -r ".[] | select(.Organisation.name==\"ORG_$((id-1))\") | .Organisation.id")
    if [[ -z "$org_id" ]]; then
      echo "[!] ERROR: Unable to find ID of ORG_$((id-1)) on instance $id"
      exit 1
    fi
  else
    echo "[+] Getting ID of ORG_$id on instance $id"
    org_id=$(curl -s -X GET "http://${HOSTS[$id]}/organisations/index.json" \
      -H "Authorization: ${AUTHS[$id]}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      | jq -r ".[] | select(.Organisation.name==\"ORG_$id\") | .Organisation.id")

    if [[ -z "$org_id" ]]; then
      echo "[!] ERROR: Unable to find ID of ORG_$id on instance $id"
      exit 1
    fi
  fi

  echo "[+] Setting ORG_$id as host organisation via cake on instance $id"
  docker exec -i "misp-docker-misp_$id-1" \
    bash -c "cd /var/www/MISP && sudo -u www-data /var/www/MISP/app/Console/cake Admin setSetting 'MISP.host_org_id' $org_id"

  # Create a new admin user for this organisation
  echo "[+] Creating new admin user for ORG_$id on instance $id"
  local result
  result=$(curl -s -X POST "http://${HOSTS[$id]}/admin/users/add" \
    -H "Authorization: ${AUTHS[$id]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "{
      \"email\":\"org${id}@admin.test\",
      \"org_id\":${org_id},
      \"role_id\":2
    }")

  local user_id
  user_id=$(echo "$result" | jq -r .User.id)
  local key
  key=$(echo "$result" | jq -r .User.authkey)
  if [[ -z "$user_id" || "$user_id" == "null" || -z "$key" || "$key" == "null" ]]; then
    echo "[!] ERROR: Failed to create org admin user or retrieve API key for ORG_$id"
    exit 1
  fi

  export AUTH_$id="$key"
  AUTHS_ORG[$id]="$key"
  echo "[✓] Org admin API key created and exported for instance $id"
}

# set_redis_db_settings: Set Redis database settings for a given instance
# Arguments:
#   $1: Instance index
set_redis_db_settings() {
  local id="$1"
  echo "[+] Setting redis_database for instance $id"
  docker exec -i "misp-docker-misp_${id}-1" \
    bash -c "cd /var/www/MISP && sudo -u www-data /var/www/MISP/app/Console/cake Admin setSetting 'MISP.redis_database' $((NUM_INSTANCES+id))"
  docker exec -i "misp-docker-misp_${id}-1" \
    bash -c "cd /var/www/MISP && sudo -u www-data /var/www/MISP/app/Console/cake Admin setSetting 'SimpleBackgroundJobs.redis_database' $id"
}

# create_sync_user: Create a synchronization user for an organisation on a target instance
# Arguments:
#   $1: Source organisation index
#   $2: Target instance index
create_sync_user() {
  local source="$1"  # source organisation (e.g.: 1)
  local target="$2"  # target instance (e.g.: 2)
  local target_host="${HOSTS[$target]}"

  echo "[+] Creating a sync user for ORG_$source on instance $target"

  # Get org_id of ORG_source on target instance
  local org_id
  if [ $INTERNAL_LAST_TWO ]; then
    if [ "$target" -eq "$((NUM_INSTANCES-1))" ]; then
      org_id=$(get_org_id_on_instance "$target" "$target")
    elif [ "$target" -eq "$NUM_INSTANCES" ]; then
      org_id=$(get_org_id_on_instance "$source" "$source")
    else
      org_id=$(get_org_id_on_instance "$target" "$source")
    fi
  else
    org_id=$(get_org_id_on_instance "$target" "$source")
  fi

  if [[ -z "$org_id" ]]; then
    echo "[!] ERROR: ORG_$source does not exist on instance $target"
    exit 1
  fi

  local result
  result=$(curl -s -X POST "http://${target_host}/admin/users/add" \
    -H "Authorization: ${AUTHS[$target]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "{
      \"email\":\"sync${source}on${target}@user.test\",
      \"org_id\":${org_id},
      \"role_id\":5,
      \"external_auth_required\":false,
      \"autoalert\":false,
      \"disabled\":false,
      \"change_pw\":false
    }")

  local user_id
  user_id=$(echo "$result" | jq -r .User.id)
  if [[ -z "$user_id" || "$user_id" == "null" ]]; then
    echo "[!] ERROR: Failed to create user sync${source}on${target}"
    exit 1
  fi

  # Explicitly create API key for this user
  echo "[+] Generating API key for user (ID=$user_id) on instance $target"
  local api_key_response
  api_key_response=$(curl -s -X POST "http://${target_host}/auth_keys/add/${user_id}" \
    -H "Authorization: ${AUTHS[$target]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "{
      \"user_id\": \"$user_id\",
      \"comment\": \"Sync key for ORG_${source}\"
    }")

  local key
  key=$(echo "$api_key_response" | jq -r .AuthKey.authkey_raw)

  if [[ -z "$key" || "$key" == "null" ]]; then
    echo "[!] ERROR: Failed to generate API key for user ID=$user_id"
    exit 1
  fi

  export "SYNC_KEY_${source}_ON_${target}"="$key"
  echo "[✓] API key created and exported: SYNC_KEY_${source}_ON_${target}"
}

# create_sync_server: Create a remote server entry for synchronization on a source instance pointing to a target instance
# Arguments:
#   $1: Source instance index
#   $2: Target instance index
create_sync_server() {
  local source="$1"
  local target="$2"
  local source_host="${HOSTS[$source]}"
  local target_host="${HOSTS[$target]}"
  local key_var="SYNC_KEY_${source}_ON_${target}"
  local key="${!key_var}"

  local org_id
  local internal_flag="false"

  if [ $INTERNAL_LAST_TWO ]; then
    internal_flag="true"
    if [ "$target" -eq "$((NUM_INSTANCES-1))" ]; then
      org_id=$(get_org_id_on_instance "$target" "$target")
    elif [ "$target" -eq "$NUM_INSTANCES" ]; then
      org_id=$(get_org_id_on_instance "$source" "$source")
    else
      org_id=$(get_org_id_on_instance "$source" "$target")
    fi
  else
    org_id=$(get_org_id_on_instance "$source" "$target")
  fi

  echo "[+] Creating remote server on instance $source pointing to instance $target"
  echo "MISP_${target}"
  echo "{ORG_UUIDS[target]}: ${ORG_UUIDS[$target]}"
  echo "authkey: [REDACTED]"

  local server_response
  server_response=$(curl -s -X POST "http://${source_host}/servers/add" \
    -H "Authorization: ${AUTHS[$source]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"MISP_${target}\",
      \"url\": \"http://misp_${target}\",
      \"remote_org_id\": \"${org_id}\",
      \"authkey\": \"${key}\",
      \"pull\": true,
      \"push\": true,
      \"push_sightings\": true,
      \"push_galaxy_clusters\": true,	
      \"pull_galaxy_clusters\": true,
      \"push_analyst_data\": true,
      \"pull_analyst_data\": true,
      \"internal\": ${internal_flag}
    }")
}

# create_sharing_group: Create a sharing group on instance 1
create_sharing_group() {
  local sharing_group_uuid
  sharing_group_uuid=$(uuidgen)
  local org_id
  org_id=$(get_org_id_on_instance 1 1)
  local org_uuid="${ORG_UUIDS[1]}"

  echo "[+] Creating the sharing group on instance 1"

  local result
  result=$(curl -s -X POST "http://${HOSTS[1]}/sharing_groups/add" \
    -H "Authorization: ${AUTHS[1]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "{
      \"uuid\": \"${sharing_group_uuid}\",
      \"name\": \"My Sharing Group\",
      \"description\": \"Sharing Group with X Banking Institutions\",
      \"releasability\": \"Banking Institutions\"
    }")
  local sharing_group_id
  sharing_group_id=$(echo "$result" | jq -r '.SharingGroup.id')

  if [[ -z "$sharing_group_id" || "$sharing_group_id" == "null" ]]; then
    echo "[!] ERROR: Sharing group creation failed"
    exit 1
  fi

  export SHARING_GROUP_ID="$sharing_group_id"
  echo "[✓] Sharing group created with ID $sharing_group_id"
}

# add_orgs_to_sharing_group: Add organisations to the sharing group on instance 1
# Arguments:
#   $1: Sharing group ID
add_orgs_to_sharing_group() {
  local sharing_group_id="$1"
  local source=1
  # Add organisation ORG_1 to the sharing group
  echo "[+] Adding ORG_1 to sharing group $sharing_group_id"
  curl -s -X POST "http://${HOSTS[1]}/sharing_groups/addOrg/${sharing_group_id}/${ORG_UUIDS[1]}" \
    -H "Authorization: ${AUTHS[1]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" > /dev/null
  # Get the list of target instances from CONNECTION_SCHEMA[1]
  local targets=(${CONNECTION_SCHEMA[$source]})
  if [[ ${#targets[@]} -gt 0 ]]; then
    # Only add the first server from the list
    local first_target="${targets[0]}"
    local org_id
    org_id=$(get_org_id_on_instance 1 "$first_target")
    if [[ -n "$org_id" && "$org_id" != "null" ]]; then
      echo "[+] Adding organisation $org_id to sharing group $sharing_group_id"
      curl -s -X POST "http://${HOSTS[1]}/sharing_groups/addOrg/${sharing_group_id}/${org_id}" \
        -H "Authorization: ${AUTHS[1]}" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" > /dev/null
    fi
  fi
}

# add_servers_to_sharing_group: Add remote servers to the sharing group on instance 1
# Arguments:
#   $1: Sharing group ID
add_servers_to_sharing_group() {
  local sharing_group_id="$1"
  local source=1
  for target in ${CONNECTION_SCHEMA[$source]}; do
    # Retrieve the remote server ID on instance 1
    local servers
    servers=$(curl -s -X GET "http://${HOSTS[1]}/servers/index.json" \
      -H "Authorization: ${AUTHS[1]}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json")
    local server_id
    server_id=$(echo "$servers" | jq -r ".[] | select(.Server.name==\"MISP_${target}\") | .Server.id")
    if [[ -n "$server_id" && "$server_id" != "null" ]]; then
      echo "[+] Adding server $server_id to sharing group $sharing_group_id"
      curl -s -X POST "http://${HOSTS[1]}/sharing_groups/addServer/${sharing_group_id}/${server_id}" \
        -H "Authorization: ${AUTHS[1]}" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" > /dev/null
    fi
  done
}

# --- [6] Start configuration ---

# Generate UUIDs for all organisations
generate_uuids

# Create all organisations on each instance
for i in $(printf "%s\n" "${!HOSTS[@]}" | sort -n); do
  create_all_orgs_on_instance "$i"
done

# Set host organisation and create admin user for each instance
for i in $(printf "%s\n" "${!HOSTS[@]}" | sort -n); do
  set_host_org "$i"
done

# Set Redis database settings for each instance
for i in $(printf "%s\n" "${!HOSTS[@]}" | sort -n); do
  set_redis_db_settings "$i"
done

# Create synchronization users and remote servers according to the schema
for source in $(printf "%s\n" "${!CONNECTION_SCHEMA[@]}" | sort -n); do
  for target in ${CONNECTION_SCHEMA[$source]}; do
    create_sync_user "$source" "$target"
    create_sync_server "$source" "$target"
  done
done

# Add a sharing group and link servers/organisations
create_sharing_group
add_orgs_to_sharing_group "$SHARING_GROUP_ID"
add_servers_to_sharing_group "$SHARING_GROUP_ID"

# Export environment variables to a file for later use
ENV_FILE="sync_vars.sh"
echo "#!/bin/bash" > "$ENV_FILE"

for i in "${!HOSTS[@]}"; do
  echo "export HOST_$i=\"${HOSTS[$i]}\"" >> "$ENV_FILE"
  echo "export AUTH_ADMIN_$i=\"${AUTHS[$i]}\"" >> "$ENV_FILE"
  echo "export AUTH_ORG_$i=\"${AUTHS_ORG[$i]}\"" >> "$ENV_FILE"
done

chmod +x "$ENV_FILE"

echo "[✔] Deployment finished and synchronizations configured."

# Restart Docker services to apply changes
echo "[+] Restarting Docker services to make changes effective"
$COMPOSE_CMD down
sleep 5
$COMPOSE_CMD up -d

# Prompt user for cleanup option
echo -e "\n[!] Enter 'r' to remove all containers and volumes, or any other key to exit without removal."
read -r user_choice
if [ "$user_choice" = "r" ]; then
  $COMPOSE_CMD down -v
  echo "[✓] All containers and volumes have been removed."
else
  echo "[*] Exiting without removing containers or volumes."
fi