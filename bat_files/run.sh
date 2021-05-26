# Run the bots
docker exec -i sc2-bot poetry run python /root/aiarena-client/arenaclient/run_local.py

# Save the results.json
mkdir -p temp
docker cp sc2-bot:/root/aiarena-client/arenaclient/proxy/results.json bat_files/temp/results.json

# Save the replays
mkdir -p /temp/replays
docker cp sc2-bot:/root/StarCraftII/Replays/. bat_files/temp/replays