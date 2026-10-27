# Build and publish the Windows beta

This release flow builds a Windows installer from the checked-in source. Build it on Windows; PyInstaller bundles the active operating system's runtime and libraries.

## Build the app

1. In GitHub Desktop, select the `SpotLightApp-Public` repository, confirm the working tree is clean, and use **Fetch origin** followed by **Pull origin** if offered.
2. Open the repository in File Explorer, then open PowerShell in that folder.
3. Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` if PowerShell blocks the build script. This only changes script permission for that PowerShell window.
4. Run `.\build_windows.ps1`. The script creates a local Python 3.12 environment, installs the app's required packages and PyInstaller there, and builds the app into `dist\SpotLightApp\`.
5. Open `dist\SpotLightApp\SpotLightApp.exe` and check the sign-in screen, dashboard, and Community. Use a second Windows device for a clean-install check before sharing the installer.

The build environment and output are excluded from Git. They do not belong in a source commit.

## Create the installer

1. Install Inno Setup for Windows from [jrsoftware.org](https://jrsoftware.org/isinfo.php).
2. Open `SpotLightApp.iss` in **Inno Setup Compiler**.
3. Select **Build > Compile**. The installer will appear at `Output\SpotLightApp-Setup-1.1.2.0.exe`.
4. Run that installer on your own PC first, then test the installed shortcut and sign-in. The per-user install location does not require administrator access and keeps the app's local profile/cache in the Windows user profile.

## Add it to GitHub

1. In GitHub Desktop, commit the build script, installer recipe, and this guide. Do not commit `dist`, `build`, `Output`, `.venv-build`, local API keys, or `.env` files.
2. Select **Push origin** and wait for it to finish.
3. Open the repository on GitHub.com and select **Releases > Draft a new release**.
4. Create a tag such as `v1.1.2.0` on the current `main` branch. Set the release title to `SpotLightApp Beta 1.1.2.0`.
5. Add `Output\SpotLightApp-Setup-1.1.2.0.exe` to the release assets, write concise beta notes, then publish the release.

The installer contains the desktop app and tracked media assets, not user profiles, local databases, API credentials, or the server `.env`. The app uses the home-beta server address by default; testers can change it through **Server connection settings** on the sign-in screen without editing Windows environment variables. The home-beta address works only on the configured home network. Before sharing outside that network, move the API to the public domain with HTTPS.
