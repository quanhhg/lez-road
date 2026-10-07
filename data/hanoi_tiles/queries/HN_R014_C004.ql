[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159638,105.435335,21.204948,105.483645)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159638,105.435335,21.204948,105.483645);
  node["barrier"](21.159638,105.435335,21.204948,105.483645);
);
(._; >>;);
out meta;
out count;
