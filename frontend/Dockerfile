# Cloud Run image for the widget: built with node, served by nginx.
#
# The two backend URLs are baked in at build time, because Vite replaces
# import.meta.env at compile time -- so the image is specific to the
# environment it was built for, and the build arguments below are how it
# learns which one.
FROM node:20-slim AS build

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_REST_BASE_URL=""
ARG VITE_WS_BASE_URL=""
ENV VITE_REST_BASE_URL=$VITE_REST_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
