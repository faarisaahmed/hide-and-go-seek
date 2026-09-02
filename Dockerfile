# For anywhere that takes a container: Fly, Railway, a VPS.
#   docker build -t hide-and-go-seek .
#   docker run -p 5000:5000 hide-and-go-seek
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so editing the game does not reinstall them.
COPY backend/requirements.txt backend/requirements-deploy.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements-deploy.txt

COPY backend/ ./backend/

ENV PORT=5000 DEBUG=0
EXPOSE 5000

# One worker on purpose: rooms are held in this process's memory, so a
# second worker means a second set of rooms.
CMD ["sh", "-c", "gunicorn --chdir backend -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 -b 0.0.0.0:$PORT app:app"]
