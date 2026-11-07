FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image's Yarn APT source has a stale signing key. Docker's
# Dev Container feature runs apt-get update, which fails while that source is
# enabled. Yarn is not needed in this container; the frontend builds in Docker.
RUN for source in /etc/apt/sources.list /etc/apt/sources.list.d/*; do \
      if [ -f "$source" ] && grep -q 'dl.yarnpkg.com' "$source"; then \
        rm -f "$source"; \
      fi; \
    done
