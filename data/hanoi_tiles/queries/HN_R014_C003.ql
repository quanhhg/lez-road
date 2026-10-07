[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159769,105.387175,21.205065,105.435470)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159769,105.387175,21.205065,105.435470);
  node["barrier"](21.159769,105.387175,21.205065,105.435470);
);
(._; >>;);
out meta;
out count;
