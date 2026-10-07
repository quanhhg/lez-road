[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159163,105.579814,21.204513,105.628166)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159163,105.579814,21.204513,105.628166);
  node["barrier"](21.159163,105.579814,21.204513,105.628166);
);
(._; >>;);
out meta;
out count;
