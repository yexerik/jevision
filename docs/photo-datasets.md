# Example datasets

Setup downloads the following sources locally. Images are not included in Git.
The project's [MIT License](../LICENSE) covers its original code and documentation,
not these datasets. Follow each source's license and attribution requirements when
using or redistributing downloaded content.

| Photo source | Pinned version | Selection | Local directory |
|---|---:|---|---|
| [Hymenoptera, thedatasith](https://www.kaggle.com/datasets/thedatasith/hymenoptera) | 5 | Training split: 123 ants, 121 bees | `.photo/hymenoptera/` |
| [Sea Animals, vencerlanz09](https://www.kaggle.com/datasets/vencerlanz09/sea-animals-image-dataste) | 5 | 13,711 PNG/JPEG images, 23 categories | `.photo/sea-animals/` |

The [public manifest](photo-datasets.json) records source version, archive member, relative destination, and SHA-256 for every selected photo. The downloader verifies those bytes rather than requesting an unpinned latest version. Hymenoptera validation/cover images are excluded.

## Full project setup

Follow the [quick start](../README.md#quick-start). `pnpm run setup` installs dependencies, Chromium, both photo collections, and the HTML dataset. It configures `PHOTO_ROOT=.photo` unless you already chose another root. Add your TypeSafe key and start the app; no browser import is needed.

## Download photos only

The standalone downloader needs Python 3.9+ and no extra packages or Jev key:

```sh
python3 scripts/download_photo_datasets.py
```

Allow space for roughly 375 MB of temporary ZIPs plus extracted images. A dataset is published to its final folder only after all hashes match; temporary archives are removed. Matching installations are reused. Missing, altered, or extra photos are reported instead of overwritten.

```sh
python3 scripts/download_photo_datasets.py --dataset hymenoptera
python3 scripts/download_photo_datasets.py --dataset sea-animals
python3 scripts/download_photo_datasets.py --verify
```

Use `--output PATH` for another parent folder and set `PHOTO_ROOT` to match.

## Show the photos in the app

For a standalone download, add this to `.env`, restart, and choose **Rescan folder**:

```dotenv
PHOTO_ROOT=.photo
```

An explicitly configured root can be hidden; ordinary workspace scanning skips hidden subfolders. Category folders become datasets and supply initial targets, which you can edit in dataset settings. Downloads preserve existing user photos and library metadata.

## Manual download or Kaggle authentication

If public download requires login/consent, open the source page and download version 5. Install each dataset's ZIP separately:

```sh
python3 scripts/download_photo_datasets.py --dataset hymenoptera --archive /path/to/hymenoptera.zip
python3 scripts/download_photo_datasets.py --dataset sea-animals --archive /path/to/sea-animals.zip
```

Installation still requires every selected photo to match the manifest. The manual installer needs no Kaggle credentials. For other clients, see [Kaggle documentation](https://github.com/Kaggle/kagglehub#download-dataset). Keep credentials private and review each source's license/attribution requirements before redistributing images.

## HTML validation dataset

Setup also installs 484 PNG/HTML pairs from [SALT-NLP/Design2Code-hf](https://huggingface.co/datasets/SALT-NLP/Design2Code-hf), train split, revision `9d23e96b0b8dec04d5f5c7f0486f9a267ad81a8e`.

To install separately after project dependencies:

```sh
.venv/bin/python scripts/download_design2code.py
```

The default directory is `data/Design2Code-hf/`, used by the validator. Select **Design2Code-hf → Dataset page** or use **Download Design2Code** in the tool. Custom CLI output folders do not change the UI's dataset location.

The downloader retains the dataset card and provenance, reuses complete installations, and reports incomplete/revision-mismatched ones. Optional credentials use `HUGGING_FACE_API` in `.env` or `HF_TOKEN` in the shell.

Some HTML references use `rick.jpg`, which is absent from the pairs. Missing assets and differing viewports can affect screenshot comparisons. This collection is separate from photo tools and ignored by Git.

## Labels and prototype validation

Folder labels do not supply audited counts, instance boxes, or query relevance. HTML/reference pairs do not supply defect inventories. Use the [tool guides](../README.md#tools) to choose suitable labels and metrics. Group related images/crops/viewports when separating development from confirmation; downloading examples does not establish accuracy.
