[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.113803,105.627782,21.159166,105.676134)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.113803,105.627782,21.159166,105.676134);
  node["barrier"](21.113803,105.627782,21.159166,105.676134);
);
(._; >>;);
out meta;
out count;
