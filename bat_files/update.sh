# Copy over custom run_local.py
docker cp ../TooManyStalkers/sc2/docker/custom_run_local.py sc2-bot:/root/aiarena-client/arenaclient/run_local.py

# Copy TooManyStalkersBot
docker cp ../TooManyStalkers/. sc2-bot:/root/StarCraftII/Bots/TooManyStalkers
# Copy DummyBot
docker cp ../DummyBot/. sc2-bot:/root/StarCraftII/Bots/DummyBot