FROM node:20-alpine

# ADR-0006 compliance for opaque images: self-contained without volume mounts
RUN npm install -g @upstash/context7-mcp@2.1.2

EXPOSE 3010

ENV CONTEXT7_PORT=3010
ENV CONTEXT7_API_KEY=""

CMD ["sh", "-c", "if [ -n \"$CONTEXT7_API_KEY\" ]; then context7-mcp --transport http --port ${CONTEXT7_PORT} --api-key ${CONTEXT7_API_KEY}; else context7-mcp --transport http --port ${CONTEXT7_PORT}; fi"]
