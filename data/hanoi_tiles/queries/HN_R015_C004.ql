[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.204814,105.435467,21.250124,105.483792)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.204814,105.435467,21.250124,105.483792);
  node["barrier"](21.204814,105.435467,21.250124,105.483792);
);
(._; >>;);
out meta;
out count;
