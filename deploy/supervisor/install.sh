#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 3 ]; then
  printf 'Usage: %s PROJECT_PATH VENV_PATH APP_USER\n' "$0" >&2
  exit 2
fi

project_path=$1
venv_path=$2
app_user=$3
template_directory="$project_path/deploy/supervisor"
supervisor_config_directory=/etc/supervisor/conf.d
celery_state_directory=/var/lib/nutrifood
programs=(nutrifood nutrifood-celery-worker nutrifood-celery-beat)

if [ ! -d "$template_directory" ]; then
  printf 'Supervisor template directory not found: %s\n' "$template_directory" >&2
  exit 1
fi
if [ ! -x "$venv_path/bin/uvicorn" ] || [ ! -x "$venv_path/bin/celery" ]; then
  printf 'Application executables are missing from virtual environment: %s\n' "$venv_path" >&2
  exit 1
fi
if ! id "$app_user" >/dev/null 2>&1; then
  printf 'Application user does not exist: %s\n' "$app_user" >&2
  exit 1
fi

app_group="$(id -gn "$app_user")"
install -d -m 0750 -o "$app_user" -g "$app_group" "$celery_state_directory"

for template in "$template_directory"/*.conf; do
  rendered_config="$(< "$template")"
  rendered_config="${rendered_config//__PROJECT_PATH__/$project_path}"
  rendered_config="${rendered_config//__VENV_PATH__/$venv_path}"
  rendered_config="${rendered_config//__APP_USER__/$app_user}"

  if [[ "$rendered_config" == *"__"* ]]; then
    printf 'Unresolved placeholder in Supervisor template: %s\n' "$template" >&2
    exit 1
  fi

  config_tmp="$(mktemp)"
  trap 'rm -f "$config_tmp"' EXIT
  printf '%s\n' "$rendered_config" > "$config_tmp"
  install -m 0644 "$config_tmp" "$supervisor_config_directory/$(basename "$template")"
  rm -f "$config_tmp"
  trap - EXIT
done

supervisorctl reread
supervisorctl update
supervisorctl restart "${programs[@]}"
supervisorctl status "${programs[@]}"
