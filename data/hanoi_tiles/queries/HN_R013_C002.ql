[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.114709,105.338912,21.159992,105.387178)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.114709,105.338912,21.159992,105.387178);
  node["barrier"](21.114709,105.338912,21.159992,105.387178);
);
(._; >>;);
out meta;
out count;
