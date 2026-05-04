FROM gdssingapore/airbase:node-22-builder AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM gdssingapore/airbase:node-22
WORKDIR /app
COPY --from=builder --chown=app:app /app/node_modules ./node_modules
COPY --chown=app:app package.json ./
COPY --chown=app:app index.js ./
COPY --chown=app:app public ./public
USER app
CMD ["node", "index.js"]
