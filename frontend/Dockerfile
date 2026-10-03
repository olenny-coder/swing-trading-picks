# Static-only image: builds the Next.js export and serves it with nginx.
#
# NOTE: the recommended deployment is the single-service root Dockerfile, where
# FastAPI serves both the API and this UI on one URL. Use this image only if you
# want to host the frontend separately (then set NEXT_PUBLIC_API_BASE to the
# backend origin at build time).
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 80
