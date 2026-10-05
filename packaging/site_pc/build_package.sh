#!/usr/bin/env bash
set -euo pipefail
ROOT=NMTPL_PC_SITE_SOFTWARE_R7
PAY="$ROOT/payload"
rm -rf "$ROOT"
mkdir -p "$PAY"

files=(
  app/models.py
  app/site_models.py
  app/routers/sites.py
  app/routers/site_ops.py
  app/services/site_context.py
  app/services/tiom_location_erp.py
  app/services/wb_mapping.py
  app/static/admin_master_ops.js
  app/static/central.html
  app/static/site.js
  app/static/site_ops.js
  app/static/site_master_ops.js
  app/static/site.html
  app/static/simple_field_v1.js
  app/static/simple_field_v1.css
)

for f in "${files[@]}"; do
  test -f "$f"
  mkdir -p "$PAY/$(dirname "$f")"
  cp "$f" "$PAY/$f"
done

mkdir -p "$PAY/app"
cp packaging/pc_site_main.py "$PAY/app/main.py"
cp packaging/site_pc/INSTALL_PC_SITE_SOFTWARE.bat "$ROOT/"
cp packaging/site_pc/INSTALL_PC_SITE_SOFTWARE.ps1 "$ROOT/"
cp packaging/site_pc/ROLLBACK_PC_SITE_SOFTWARE.bat "$ROOT/"
cp packaging/site_pc/ROLLBACK_PC_SITE_SOFTWARE.ps1 "$ROOT/"
cp packaging/site_pc/README_FIRST.txt "$ROOT/"

python -m py_compile   "$PAY/app/main.py"   "$PAY/app/models.py"   "$PAY/app/site_models.py"   "$PAY/app/routers/sites.py"   "$PAY/app/routers/site_ops.py"   "$PAY/app/services/site_context.py"   "$PAY/app/services/tiom_location_erp.py"

node --check "$PAY/app/static/admin_master_ops.js"
node --check "$PAY/app/static/site.js"
node --check "$PAY/app/static/site_ops.js"
node --check "$PAY/app/static/site_master_ops.js"
node --check "$PAY/app/static/simple_field_v1.js"

grep -q "site_id == 'TIOM'" "$PAY/app/main.py"
grep -q "Desktop operations shell" "$PAY/app/static/simple_field_v1.css"
grep -q "delete defs.VEHICLE" "$PAY/app/static/site_master_ops.js"
grep -q "assigned_equipment" "$PAY/app/routers/site_ops.py"
grep -q "Enable-ScheduledTask" "$ROOT/INSTALL_PC_SITE_SOFTWARE.ps1"
grep -q "0.0.0.0" "$ROOT/INSTALL_PC_SITE_SOFTWARE.ps1"

cat > "$ROOT/PACKAGE_MANIFEST.txt" <<EOF
package=NMTPL_PC_SITE_SOFTWARE_R7
source_main_commit=2ed0c6413c8bb96d9129141e5eced7cad7ef8ee0
pc_main=packaging/pc_site_main.py
payload_files=${#files[@]}
validated_python=true
validated_javascript=true
EOF
