NMTPL PC MERGE R11
==================

Purpose
-------
Merge all finalized SOCP/KOCP temp-server updates into the PC server while
preserving PC-local changes made after the previous R7 PC package.

Source freeze
-------------
Temp/live source: 99dcf176873a7e740afc4b745b6920db698c9033

Included changes
----------------
- Dedicated SOCP and KOCP operational dashboards.
- Separate SOCP blue/steel and KOCP earth/amber themes.
- Compact high-contrast software-style entry screens.
- Multi-row Trip/WB/HSD entry.
- KOCP single Production Entry: Material determines Coal vs OB.
- KOCP HMR captured inside Production Entry, not a separate tab.
- Attendance and Shift Setup removed from SOCP/KOCP workflow.
- Fleet/Loader/Excavator/Driver/Destination moved to derived analytics/reporting.
- ERP-derived fleet status (active/breakdown/no activity).
- Site Map saved link display + Google/My Maps preview support.
- Site assignment and master validation improvements.
- TIOM remains a separate /tiom application.

How the installer protects PC work
----------------------------------
1. It compares each affected PC file with the previous R7 PC baseline.
2. Unchanged R7 files are safely replaced with R11.
3. Already-current files are left as-is.
4. PC-local modifications are three-way merged with R11 when Git is available.
5. If a real merge conflict exists, NOTHING is installed.
6. A conflict report and PC_CURRENT / R7_BASE / R11_LATEST copies are produced.
7. Before successful installation, every affected file is backed up.
8. Python/app import/server health are checked.
9. If validation or startup fails, the installer automatically restores the backup.

Install
-------
1. Extract the ZIP.
2. Right-click INSTALL_PC_MERGE_R11.bat -> Run as administrator.
3. If asked, enter the current NMTPL_Server_v0_1 folder.
4. Read PC_MERGE_R11_REPORT.txt in the project root after completion.

If the installer reports a conflict
-----------------------------------
No source file has been overwritten.
Use the path shown in PC_MERGE_R11_REPORT.txt. The conflict folder contains the
PC version, R7 base and R11 latest copy of each conflicting file.

The package does NOT replace
----------------------------
.env
PostgreSQL data
Gmail credentials/tokens
database backups
logs
WB data
other project files not listed in this merge package.
