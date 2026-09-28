# Azure deployment storage settings

The application defaults to SQLite and local file storage, so development does
not require Azure services. For a low-cost Azure App Service deployment, use a
single app instance and enable persistent storage for the container:

- Set `WEBSITE_ENABLE_APP_SERVICE_STORAGE` to `true`.
- Set `DATABASE_PATH` to `/home/filingscope.db`.
- Set `GROQ_API_KEY` in App Service application settings; do not add it to the
  image or source repository.
- Optionally set `AZURE_STORAGE_CONNECTION_STRING` and
  `AZURE_STORAGE_CONTAINER` to store PDFs in Azure Blob Storage rather than on
  the App Service filesystem.

SQLite is appropriate for a single app instance and modest request volume. Do
not scale this configuration to multiple instances; each instance would not
share a reliable SQLite database. Move to a managed database before scaling
horizontally.

Blob Storage and App Service consume Azure resources and may use the account's
credits. Azure budget alerts notify you but are not a hard spending limit.
Check the current pricing and configure a budget alert before deployment. The
credit balance does not guarantee the application will remain free after the
credits expire.