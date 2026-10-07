[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.248912,105.724729,21.294302,105.773154)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.248912,105.724729,21.294302,105.773154);
  node["barrier"](21.248912,105.724729,21.294302,105.773154);
);
(._; >>;);
out meta;
out count;
