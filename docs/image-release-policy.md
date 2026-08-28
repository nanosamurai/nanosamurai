# Image release policy

The Compose defaults use immutable `sha-<full-git-sha>` tags for all nanosamurai
service images. A pin identifies both the service source revision and the image
that passed its publication workflow. These checked-in pins are the primary
image-selection mechanism for the evaluator. Image environment variables are
optional overrides for local development, evaluation of another immutable
release, or rollback; users do not need to set them for the normal quickstart.

Before updating a default pin:

1. Confirm CI and the image-publication workflow succeeded for the source SHA.
2. Pull the exact tag from GHCR.
3. Validate the default Compose model and the observability override.
4. Run the applicable smoke-test tiers.
5. Verify the package can be pulled anonymously before announcing the release.
6. Update the rollout record with the tested SHAs and known limitations.

Infrastructure images use explicit version tags rather than `latest`. Automated
dependency updates must still pass the same Compose and smoke validation.

Future stable releases may add semantic-version tags. An `edge` tag may be
provided for convenience, but it must never be the default in this repository.
