[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.203271,105.820851,21.248687,105.869289)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.203271,105.820851,21.248687,105.869289);
  node["barrier"](21.203271,105.820851,21.248687,105.869289);
);
(._; >>;);
out meta;
out count;
