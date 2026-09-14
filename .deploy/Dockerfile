# congress-demo / web — the React build, served by unprivileged nginx.
# Multi-stage: no toolchain and no node_modules reach the container that faces
# the internet. The build context is the site directory; the checkout is repo/.
ARG NODE_VERSION=20
FROM node:${NODE_VERSION}-alpine AS build
WORKDIR /src
# Lockfile first so a source change does not reinstall the toolchain.
COPY repo/frontend/package.json repo/frontend/package-lock.json ./
RUN npm ci
COPY repo/frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
