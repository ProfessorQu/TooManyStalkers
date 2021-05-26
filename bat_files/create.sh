# Pull image
docker pull burnysc2/python-sc2-docker:release-python_3.7-sc2_4.10_arenaclient_burny

# Force-remove previous container called 'sc2-bot'
docker rm -f sc2-bot

# Create container
docker run -it -d --name sc2-bot burnysc2/python-sc2-docker:release-python_3.7-sc2_4.10_arenaclient_burny

# List available maps
docker exec -i sc2-bot bash -c "ls -l /root/StarCraftII/maps"

# Install bot requirements
docker exec -i sc2-bot poetry add "burnysc2>=0.12.12"

# Copy over custom run_local.py
docker cp ../TooManyStalkers/sc2/docker/custom_run_local.py sc2-bot:/root/aiarena-client/arenaclient/run_local.py
