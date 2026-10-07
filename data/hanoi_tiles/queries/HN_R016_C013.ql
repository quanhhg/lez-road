[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.248187,105.869286,21.293617,105.917753)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.248187,105.869286,21.293617,105.917753);
  node["barrier"](21.248187,105.869286,21.293617,105.917753);
);
(._; >>;);
out meta;
out count;
