# Start arenaclient server
# docker exec -i sc2-bot python /root/aiarena-client/arenaclient/proxy/server.py -f &
# Alternatively set in Dockerfile as last line:
# ENTRYPOINT [ "python", "proxy/server.py", "-f" ]

# Run the match(es)
docker exec -i sc2-bot poetry run python /root/aiarena-client/arenaclient/run_local.py

# Display error logs
docker exec -i sc2-bot bash -c "tree /root/aiarena-client/arenaclient/logs"
docker exec -i sc2-bot bash -c "echo Basic bot error log:"
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/logs/1/basic_bot/stderr.log"
docker exec -i sc2-bot bash -c "echo Loser bot error log:"
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/logs/1/loser_bot/stderr.log"
docker exec -i sc2-bot bash -c "echo Proxy results.json:"
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/proxy/results.json"

# Display result.json
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/proxy/results.json"

# Copy results.json to host machine
mkdir -p temp
docker cp sc2-bot:/root/aiarena-client/arenaclient/proxy/results.json temp/results.json

# Copy replay to host machine
docker exec -i sc2-bot bash -c "tree /root/StarCraftII/Replays"
mkdir -p temp/replays
docker cp sc2-bot:/root/StarCraftII/Replays/. temp/replays