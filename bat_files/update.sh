# Copy the bot
docker cp ../TooManyStalkers/. sc2-bot:/root/StarCraftII/Bots/TooManyStalkers
# Copy the run file
docker cp ../TooManyStalkers/sc2/docker/custom_run_local.py sc2-bot:/root/aiarena-client/arenaclient/run_local.py