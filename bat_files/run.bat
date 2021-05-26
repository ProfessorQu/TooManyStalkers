rem Start arenaclient server
rem docker exec -i sc2-bot python /root/aiarena-client/arenaclient/proxy/server.py -f &
rem Alternatively set in Dockerfile as last line:
rem ENTRYPOINT [ "python", "proxy/server.py", "-f" ]

rem Run the match(es)
docker exec -i sc2-bot poetry run python /root/aiarena-client/arenaclient/run_local.py

rem Display error logs
docker exec -i sc2-bot bash -c "tree /root/aiarena-client/arenaclient/logs"
docker exec -i sc2-bot bash -c "echo TooManyStalkersBot error log:"
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/logs/1/TooManyStalkers/stderr.log"

rem Display result.json
docker exec -i sc2-bot bash -c "echo Proxy results.json:"
docker exec -i sc2-bot bash -c "cat /root/aiarena-client/arenaclient/proxy/results.json"

rem Copy results.json to host machine
mkdir temp
docker cp sc2-bot:/root/aiarena-client/arenaclient/proxy/results.json temp/results.json

rem Copy replay to host machine
docker exec -i sc2-bot bash -c "tree /root/StarCraftII/Replays"
mkdir temp/replays
docker cp sc2-bot:/root/StarCraftII/Replays/. temp/replays

rem Copy log file
mkdir temp/logs
docker cp sc2-bot:/root/aiarena-client/arenaclient/logs/. temp/logs