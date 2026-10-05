NMTPL PC SITE SOFTWARE R1
==========================

One consolidated PC update for SOCP/KOCP.

CHANGES
-------
- TIOM removed from generic Site app; /site/TIOM redirects to /tiom.
- Site switcher shows SOCP and KOCP only.
- Desktop SOCP/KOCP uses full left-navigation software layout.
- Smaller screens retain simple field-entry behavior.
- One Equipment / Vehicle master in the site UI.
- Equipment Type and Ownership use guided dropdowns.
- ERP Category is automatic/read-only.
- Existing Tripper/Dumper/Truck rows are recognised semantically.
- Trip entry enforces active SOCP/KOCP equipment assignment.
- LAN/background server uses 0.0.0.0:8000 and LocalSubnet firewall access.

INSTALL
-------
1. Extract this ZIP.
2. Right-click INSTALL_PC_SITE_SOFTWARE.bat and choose Run as administrator.
3. If asked, enter the NMTPL_Server_v0_1 folder path.
4. The installer backs up every file it replaces.
5. It validates Python import and server health before reporting success.
6. Open PC_SITE_SOFTWARE_R7_RESULT.txt in the project folder.

SAFETY
------
This package does NOT replace .env, PostgreSQL data, Gmail tokens/credentials, database dumps or logs.
Use ROLLBACK_PC_SITE_SOFTWARE.bat if a rollback is needed.
