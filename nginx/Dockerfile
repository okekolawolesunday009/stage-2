FROM nginx:stable-alpine

# Install envsubst (gettext) so the nginx start command that uses envsubst works
RUN apk add --no-cache gettext

# Keep the upstream image's default files; the compose command will render the template
# and run nginx in the foreground. No entrypoint change required.