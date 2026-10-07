[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.294085,105.724950,21.339475,105.773391)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.294085,105.724950,21.339475,105.773391);
  node["barrier"](21.294085,105.724950,21.339475,105.773391);
);
(._; >>;);
out meta;
out count;
