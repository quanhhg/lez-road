[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.978462,105.579114,21.023811,105.627406)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.978462,105.579114,21.023811,105.627406);
  node["barrier"](20.978462,105.579114,21.023811,105.627406);
);
(._; >>;);
out meta;
out count;
