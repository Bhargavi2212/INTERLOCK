# Deploy commands (Bhargavi runs these)

PowerShell, from the repo root, in **your own GCP project** (not the hackathon account). Claude Code never runs these and never sees the key. Run the blocks in order; each says how to check it worked.

Replace `<PROJECT_ID>` once in block 0. Everything else uses the variables.

---

## 0. Variables and login

```powershell
gcloud auth login
$PROJECT = "<PROJECT_ID>"
$REGION  = "us-central1"
$BUCKET  = "$PROJECT-interlock"
$SA      = "interlock-run@$PROJECT.iam.gserviceaccount.com"
gcloud config set project $PROJECT
```

Check: `gcloud config get-value project` prints your project id.

## 1. Enable APIs

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com firestore.googleapis.com storage.googleapis.com iamcredentials.googleapis.com
```

Check: `gcloud services list --enabled` lists all seven.

## 2. Firestore (Native mode)

```powershell
gcloud firestore databases create --location=$REGION --type=firestore-native
```

Check: `gcloud firestore databases list` shows `(default)`, type `FIRESTORE_NATIVE`.

## 3. Bucket

```powershell
gcloud storage buckets create "gs://$BUCKET" --location=$REGION --uniform-bucket-level-access
```

Check: `gcloud storage buckets describe "gs://$BUCKET"` answers.

## 4. Service account and roles

```powershell
gcloud iam service-accounts create interlock-run --display-name "Interlock Cloud Run"
gcloud projects add-iam-policy-binding $PROJECT --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor --condition=None
gcloud projects add-iam-policy-binding $PROJECT --member "serviceAccount:$SA" --role roles/datastore.user --condition=None
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectAdmin
gcloud iam service-accounts add-iam-policy-binding $SA --member "serviceAccount:$SA" --role roles/iam.serviceAccountTokenCreator
```

The last line lets the service sign upload URLs without a key file (`ARCHITECTURE.md` §1a).

Check: `gcloud iam service-accounts get-iam-policy $SA` shows `serviceAccountTokenCreator`.

## 5. Secrets (typed at a hidden prompt; never piped, never in a command)

Run this block once per secret: first with `$NAME = "GEMINI_API_KEY"`, then with `$NAME = "ACCESS_CODE"`.

```powershell
$NAME  = "GEMINI_API_KEY"
$path  = Join-Path $env:TEMP "interlock-secret.tmp"
$sec   = Read-Host "Value for $NAME" -AsSecureString
$bstr  = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[IO.File]::WriteAllText($path, $plain)          # no trailing newline
gcloud secrets create $NAME --replication-policy=automatic --data-file=$path
Remove-Item $path -Force
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
Remove-Variable plain, sec, bstr
```

To change a secret later, use the same block with `gcloud secrets versions add $NAME --data-file=$path` in place of `create`.

Check: `gcloud secrets list` shows both names (values are never shown), and `Test-Path $path` is `False`.

## 6. Deploy (repeat this block after phases 0, 2, 3, 4 and 6)

Model strings are not secrets. Copy them from your `.env` into the variables below yourself.

```powershell
$MODEL_HYDROGEN  = "<from .env>"
$MODEL_ARGON     = "<from .env>"
$MODEL_CARBON    = "<from .env>"
$MODEL_NEON      = "<from .env>"
$MODEL_DECISIONS = "<from .env>"
$MANAGED_AGENT   = "<from .env>"

$sha = git rev-parse --short HEAD
gcloud run deploy interlock --source . --region $REGION `
  --service-account $SA `
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,ACCESS_CODE=ACCESS_CODE:latest" `
  --set-env-vars "APP_VERSION=$sha,MODEL_HYDROGEN=$MODEL_HYDROGEN,MODEL_ARGON=$MODEL_ARGON,MODEL_CARBON=$MODEL_CARBON,MODEL_NEON=$MODEL_NEON,MODEL_DECISIONS=$MODEL_DECISIONS,MANAGED_AGENT=$MANAGED_AGENT,GCP_PROJECT=$PROJECT,GCP_REGION=$REGION,GCS_BUCKET=$BUCKET,FIRESTORE_DATABASE=(default)" `
  --timeout 900 --memory 2Gi --cpu 2 --min-instances 1 --max-instances 1 --no-cpu-throttling `
  --allow-unauthenticated
```

The first deploy asks to create an Artifact Registry repository: answer `Y`. The upload respects `.gcloudignore` (no `.env`, `.venv`, `data/` or PDFs).

**If the build fails with a permission error** (common in a new project), give the build service account the builder role, then deploy again:

```powershell
$PN = gcloud projects describe $PROJECT --format "value(projectNumber)"
gcloud projects add-iam-policy-binding $PROJECT --member "serviceAccount:$PN-compute@developer.gserviceaccount.com" --role roles/run.builder --condition=None
```

## 7. Service URL and bucket CORS (once, after the first deploy)

```powershell
# Cloud Run serves the same service at two addresses; allow both.
$urls = (gcloud run services describe interlock --region $REGION --format json | ConvertFrom-Json).metadata.annotations.'run.googleapis.com/urls' | ConvertFrom-Json
$URL  = gcloud run services describe interlock --region $REGION --format "value(status.url)"
$origins = (@($urls) + @($URL) | Select-Object -Unique | ForEach-Object { "`"$_`"" }) -join ", "
$cors = "[{`"origin`": [$origins], `"method`": [`"PUT`"], `"responseHeader`": [`"Content-Type`"], `"maxAgeSeconds`": 3600}]"
$corsPath = Join-Path $env:TEMP "interlock-cors.json"
[IO.File]::WriteAllText($corsPath, $cors)
gcloud storage buckets update "gs://$BUCKET" --cors-file=$corsPath
Remove-Item $corsPath
$URL
```

Check: `gcloud storage buckets describe "gs://$BUCKET" --format "value(cors_config)"` shows **both** service URLs (`interlock-<project number>.us-central1.run.app` and `interlock-<hash>-uc.a.run.app`) and `PUT`.

## 8. Check the live service (after every deploy)

```powershell
$URL = gcloud run services describe interlock --region $REGION --format "value(status.url)"
curl.exe -s "$URL/health"
git rev-parse --short HEAD
```

Check: `/health` returns `{"status":"ok","version":"<sha>"}` and the version equals the sha printed below it. Open `$URL` on a phone: the page shows "Interlock" and the same version.

Send Claude Code only the URL.
