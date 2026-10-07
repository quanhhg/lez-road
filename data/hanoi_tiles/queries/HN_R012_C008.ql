[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.068628,105.627592,21.113991,105.675929)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.068628,105.627592,21.113991,105.675929);
  node["barrier"](21.068628,105.627592,21.113991,105.675929);
);
(._; >>;);
out meta;
out count;
