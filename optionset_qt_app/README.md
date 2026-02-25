# Dataverse OptionSet Helper – Qt Desktop App

PySide6 desktop application for managing Dataverse OptionSets (global & local choices).

## Features

- **Authenticate** via `.env` file (OAuth2 client-credentials flow)
- **List / Search** global OptionSets with real-time filtering
- **View** OptionSet options in a sortable, searchable table
- **Create** new global OptionSets (with optional initial options from CSV/JSON)
- **Insert single** option into an existing OptionSet
- **Bulk-Insert** options from CSV or JSON (with duplicate detection via safe-insert)
- **Bulk-Update** option labels from CSV or JSON
- **Bulk-Delete** options from CSV or JSON
- All bulk operations run in **batches of 50** with automatic token refresh, timestamped logging, and a progress dialog
- **Settings dialog** with `.env` file browser and connection preview (Environment URL, Tenant ID, Client ID)
- Persistent settings – the app remembers your last `.env` path between sessions
- **Standalone executable** – build a single `.exe` with PyInstaller (no Python required on the target machine)

## Prerequisites

- Python 3.10+
- A **Dataverse environment** with an App Registration (service principal) that has appropriate permissions
- A `.env` file with your credentials (see below)

## Setting Up the `.env` File

Create a file named `.env` in the **parent** `OptionSetHelper/` directory (or any location you prefer — you can browse to it from *File → Settings*).

The file must contain the following four keys:

```env
client_id=<your-azure-ad-app-client-id>
client_secret=<your-azure-ad-app-client-secret>
tenant_id=<your-azure-ad-tenant-id>
environmentUrl=https://<your-org>.crm4.dynamics.com/
```

| Key               | Description                                                                                         |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| `client_id`       | The **Application (client) ID** from your Azure AD App Registration                                |
| `client_secret`   | A **client secret** generated under *Certificates & secrets* in the App Registration                |
| `tenant_id`       | The **Directory (tenant) ID** of your Azure AD tenant                                               |
| `environmentUrl`  | The root URL of your Dataverse environment (e.g. `https://contoso.crm4.dynamics.com/`). Include the trailing `/`. |

> **Where to find these values:**
>
> 1. Go to the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
> 2. Select (or create) your App Registration.
> 3. Copy **Application (client) ID** → `client_id`.
> 4. Copy **Directory (tenant) ID** → `tenant_id`.
> 5. Go to **Certificates & secrets → Client secrets → New client secret**, copy the value → `client_secret`.
> 6. In the [Power Platform admin center](https://admin.powerplatform.microsoft.com/), find your environment's URL → `environmentUrl`.
>
> Make sure the App Registration has the **Dynamics CRM** API permission (`user_impersonation`) or is registered as an **Application User** in Dataverse with the appropriate security role.

⚠️ **Never commit the `.env` file to source control.** It is already listed in `.gitignore`.

## Quick Start

```bash
cd optionset_qt_app
pip install -r requirements.txt
python main.py
```

On first launch, go to **File → Settings** and browse to your `.env` file. The app will authenticate automatically and remember the path for future sessions.

## Building a Standalone Executable

You can package the app as a single `.exe` using PyInstaller:

```bash
cd optionset_qt_app
pip install pyinstaller
pyinstaller DataverseOptionSetHelper.spec
```

The executable will be created at `dist/DataverseOptionSetHelper.exe`. Place your `.env` file next to the `.exe` (or use *File → Settings* to browse to it at runtime).

## CSV / JSON File Format

### CSV (headerless, two columns)

```
Label Text,100
Another Label,200
```

- **Column 1** – Option label (string)
- **Column 2** – Option value (integer)

### JSON (array of objects)

```json
[
  { "label": "Label Text", "value": 100 },
  { "label": "Another Label", "value": 200 }
]
```

## Project Structure

```
optionset_qt_app/
├── main.py                          # Entry point
├── requirements.txt                 # PySide6, requests, python-dotenv, tqdm
├── DataverseOptionSetHelper.spec    # PyInstaller spec for building .exe
├── README.md
├── optionset_qt/                    # Main package
│   ├── __init__.py
│   ├── app.py                       # QApplication bootstrap & stylesheet loader
│   ├── main_window.py               # MainWindow (connects UI ↔ Controllers)
│   ├── ui/
│   │   └── main_window_ui.py        # Programmatic UI layout (menus, tables, log)
│   ├── views/
│   │   ├── settings_dialog.py       # .env file browser & connection preview
│   │   └── bulk_progress_dialog.py  # Bulk-operation progress dialog
│   ├── models/
│   │   └── optionset_model.py       # OptionSetInfo / OptionValueInfo dataclasses
│   ├── controllers/
│   │   └── main_controller.py       # QThread workers (Auth, List, Bulk ops, …)
│   └── assets/
│       └── styles.qss               # Global QSS stylesheet
└── tests/
    └── test_main.py
```
