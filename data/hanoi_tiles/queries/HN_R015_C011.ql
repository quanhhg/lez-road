[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.203512,105.772680,21.248915,105.821104)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.203512,105.772680,21.248915,105.821104);
  node["barrier"](21.203512,105.772680,21.248915,105.821104);
);
(._; >>;);
out meta;
out count;
