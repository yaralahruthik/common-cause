import { useRoute } from "./route";
import { ConcentrationScreen } from "./screens/Concentration";
import { ExposureScreen } from "./screens/Exposure";
import { Landing } from "./screens/Landing";
import { PortfolioScreen } from "./screens/Portfolio";

export function App() {
  const route = useRoute();
  switch (route.screen) {
    case "landing":
      return <Landing />;
    case "portfolio":
      return <PortfolioScreen key={route.portfolioId} portfolioId={route.portfolioId} />;
    case "exposure":
      return <ExposureScreen key={route.portfolioId} portfolioId={route.portfolioId} />;
    case "concentration":
      return (
        <ConcentrationScreen
          key={`${route.portfolioId}/${route.concentrationId}`}
          portfolioId={route.portfolioId}
          concentrationId={route.concentrationId}
        />
      );
  }
}
