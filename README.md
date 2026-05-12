# Sumire Miyachi official blog archive

Static archive site for Sumire Miyachi official blog posts.

## Local update

```powershell
pip install -r requirements.txt
python scripts/update_blog.py
python -m http.server 8000
```

Open `http://localhost:8000/`.

## GitHub Pages

Enable Pages from the repository settings and publish from the `main` branch root. The workflow in `.github/workflows/update-blog.yml` refreshes the blog archive, current profile photo, profile-photo history, and monthly greeting archive every hour. It can also be run manually from the Actions tab.
