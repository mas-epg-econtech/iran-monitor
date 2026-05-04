# Iran Monitor — Airbase container.
# Multi-stage build: install Node deps in a build stage, then copy the
# resulting node_modules + app files into a clean runtime image.
# Uses GovTech's airbase:node-22 base which is the platform-supported
# image for Airbase deployments.

FROM gdssingapore/airbase:node-22 AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --production

FROM gdssingapore/airbase:node-22
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY index.js ./
COPY public ./public
EXPOSE 3000
CMD ["node", "index.js"]
