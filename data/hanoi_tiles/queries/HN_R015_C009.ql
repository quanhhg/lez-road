[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.203952,105.676336,21.249329,105.724732)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.203952,105.676336,21.249329,105.724732);
  node["barrier"](21.203952,105.676336,21.249329,105.724732);
);
(._; >>;);
out meta;
out count;
