[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.068813,105.579463,21.114163,105.627785)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.068813,105.579463,21.114163,105.627785);
  node["barrier"](21.068813,105.579463,21.114163,105.627785);
);
(._; >>;);
out meta;
out count;
